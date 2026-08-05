import asyncio

import pytest

from hair_tryon.domain import (
    AttemptLimitExceeded,
    GenerationSet,
    GenerationSetState,
    ViewName,
    ViewState,
)
from hair_tryon.orchestration import GenerationOrchestrator
from hair_tryon.providers import (
    GenerationRequest,
    ProviderError,
    ProviderErrorCode,
    ProviderImage,
    ProviderResult,
)


def request(view: ViewName, attempt: int = 1) -> GenerationRequest:
    return GenerationRequest(
        generation_set_id="set-1",
        view=view,
        attempt=attempt,
        prompt=f"generate {view.value}",
        prompt_version=f"{view.value}-v1",
        images=(ProviderImage("source", "image/jpeg", b"source"),),
    )


def result(view: ViewName, attempt: int = 1) -> ProviderResult:
    return ProviderResult(
        provider_mode="fake",
        model="fake-deterministic",
        image_bytes=f"{view.value}-{attempt}".encode(),
        mime_type="image/png",
        request_id=f"{view.value}-{attempt}",
        is_fake=True,
    )


class ConcurrentProvider:
    def __init__(self) -> None:
        self.started: list[ViewName] = []
        self._both_started = asyncio.Event()

    async def generate(self, generation_request: GenerationRequest) -> ProviderResult:
        self.started.append(generation_request.view)
        if generation_request.view in (ViewName.FRONT, ViewName.SIDE):
            if {ViewName.FRONT, ViewName.SIDE}.issubset(self.started):
                self._both_started.set()
            await asyncio.wait_for(self._both_started.wait(), timeout=0.5)
        return result(generation_request.view, generation_request.attempt)


class PartialProvider:
    def __init__(self) -> None:
        self.front_ready = asyncio.Event()
        self.release_side = asyncio.Event()

    async def generate(self, generation_request: GenerationRequest) -> ProviderResult:
        if generation_request.view is ViewName.FRONT:
            return result(ViewName.FRONT)
        if generation_request.view is ViewName.SIDE:
            self.front_ready.set()
            await self.release_side.wait()
            return result(ViewName.SIDE)
        return result(ViewName.BACK)


@pytest.mark.asyncio
async def test_completed_front_is_persisted_and_visible_while_side_is_still_running() -> None:
    provider = PartialProvider()
    generation_set = GenerationSet("set-1", "H01")
    persisted: list[ViewName] = []

    async def persist(
        generation_request: GenerationRequest,
        provider_result: ProviderResult,
    ) -> str:
        persisted.append(generation_request.view)
        return f"stored-{generation_request.view.value}"

    orchestrator = GenerationOrchestrator(
        provider,
        call_timeout_seconds=1,
        result_sink=persist,
    )
    task = asyncio.create_task(
        orchestrator.run_initial(
            generation_set,
            front_request=request(ViewName.FRONT),
            side_request=request(ViewName.SIDE),
            back_request_factory=lambda front, side: request(ViewName.BACK),
        )
    )

    await asyncio.wait_for(provider.front_ready.wait(), timeout=0.5)
    await asyncio.sleep(0)

    assert persisted == [ViewName.FRONT]
    assert generation_set.view(ViewName.FRONT).state is ViewState.SUCCEEDED
    assert generation_set.view(ViewName.FRONT).final_attempt.result_id == "stored-front"
    assert generation_set.view(ViewName.SIDE).state is ViewState.RUNNING

    provider.release_side.set()
    await task


@pytest.mark.asyncio
async def test_front_and_side_run_concurrently_and_back_starts_after_both_succeed() -> None:
    provider = ConcurrentProvider()
    generation_set = GenerationSet("set-1", "H01")
    built_back_from: list[tuple[str, str]] = []

    def build_back(front: ProviderResult, side: ProviderResult) -> GenerationRequest:
        built_back_from.append((front.request_id, side.request_id))
        return request(ViewName.BACK)

    outputs = await GenerationOrchestrator(provider, call_timeout_seconds=1).run_initial(
        generation_set,
        front_request=request(ViewName.FRONT),
        side_request=request(ViewName.SIDE),
        back_request_factory=build_back,
    )

    assert set(provider.started[:2]) == {ViewName.FRONT, ViewName.SIDE}
    assert provider.started[2] is ViewName.BACK
    assert built_back_from == [("front-1", "side-1")]
    assert set(outputs) == {ViewName.FRONT, ViewName.SIDE, ViewName.BACK}
    assert generation_set.state is GenerationSetState.THREE_VIEWS_READY


class SideFailureProvider:
    def __init__(self) -> None:
        self.started: list[ViewName] = []

    async def generate(self, generation_request: GenerationRequest) -> ProviderResult:
        self.started.append(generation_request.view)
        if generation_request.view is ViewName.SIDE:
            raise ProviderError(ProviderErrorCode.SAFETY_REJECTION)
        return result(generation_request.view, generation_request.attempt)


@pytest.mark.asyncio
async def test_side_failure_preserves_front_and_never_starts_dependent_back() -> None:
    provider = SideFailureProvider()
    generation_set = GenerationSet("set-1", "H01")
    back_factory_called = False

    def build_back(front: ProviderResult, side: ProviderResult) -> GenerationRequest:
        nonlocal back_factory_called
        back_factory_called = True
        return request(ViewName.BACK)

    outputs = await GenerationOrchestrator(provider, call_timeout_seconds=1).run_initial(
        generation_set,
        front_request=request(ViewName.FRONT),
        side_request=request(ViewName.SIDE),
        back_request_factory=build_back,
    )

    assert outputs[ViewName.FRONT].request_id == "front-1"
    assert ViewName.SIDE not in outputs
    assert ViewName.BACK not in outputs
    assert set(provider.started) == {ViewName.FRONT, ViewName.SIDE}
    assert back_factory_called is False
    assert generation_set.view(ViewName.FRONT).state is ViewState.SUCCEEDED
    assert generation_set.view(ViewName.SIDE).state is ViewState.FAILED
    assert generation_set.view(ViewName.SIDE).final_attempt.error_code == "safety_rejection"
    assert generation_set.state is GenerationSetState.PARTIAL_FAILURE


class SlowProvider:
    async def generate(self, generation_request: GenerationRequest) -> ProviderResult:
        await asyncio.sleep(0.2)
        return result(generation_request.view, generation_request.attempt)


@pytest.mark.asyncio
async def test_hard_call_timeout_records_timeout_terminal_state() -> None:
    generation_set = GenerationSet("set-1", "H01")
    orchestrator = GenerationOrchestrator(SlowProvider(), call_timeout_seconds=0.01)

    output = await orchestrator.run_view(generation_set, request(ViewName.FRONT))

    assert output is None
    assert generation_set.view(ViewName.FRONT).state is ViewState.FAILED
    assert generation_set.view(ViewName.FRONT).final_attempt.error_code == "timeout"


class AttemptRecordingProvider:
    def __init__(self) -> None:
        self.attempts: list[int] = []

    async def generate(self, generation_request: GenerationRequest) -> ProviderResult:
        self.attempts.append(generation_request.attempt)
        if generation_request.attempt == 1:
            raise ProviderError(ProviderErrorCode.TECHNICAL_FAILURE)
        return result(generation_request.view, generation_request.attempt)


@pytest.mark.asyncio
async def test_retry_uses_attempt_two_as_final_without_a_third_call() -> None:
    provider = AttemptRecordingProvider()
    generation_set = GenerationSet("set-1", "H01")
    orchestrator = GenerationOrchestrator(provider, call_timeout_seconds=1)

    first = await orchestrator.run_view(generation_set, request(ViewName.FRONT, 1))
    second = await orchestrator.run_view(generation_set, request(ViewName.FRONT, 2))

    assert first is None
    assert second is not None
    assert provider.attempts == [1, 2]
    assert generation_set.view(ViewName.FRONT).final_attempt.number == 2
    assert generation_set.view(ViewName.FRONT).final_attempt.result_id == "front-2"

    with pytest.raises(AttemptLimitExceeded):
        await orchestrator.run_view(generation_set, request(ViewName.FRONT, 3))

    assert provider.attempts == [1, 2]
