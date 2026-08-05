from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from hair_tryon.domain import GenerationSet, InvalidViewTransition, ViewName
from hair_tryon.providers import (
    GenerationRequest,
    ImageProvider,
    ProviderError,
    ProviderErrorCode,
    ProviderResult,
)


BackRequestFactory = Callable[[ProviderResult, ProviderResult], GenerationRequest]
ResultSink = Callable[[GenerationRequest, ProviderResult], Awaitable[str]]


class GenerationOrchestrator:
    """Runs the approved front/side parallel then back-dependent workflow."""

    def __init__(
        self,
        provider: ImageProvider,
        *,
        call_timeout_seconds: float = 15.0,
        result_sink: ResultSink | None = None,
    ) -> None:
        self._provider = provider
        self._call_timeout_seconds = call_timeout_seconds
        self._result_sink = result_sink

    async def run_initial(
        self,
        generation_set: GenerationSet,
        *,
        front_request: GenerationRequest,
        side_request: GenerationRequest,
        back_request_factory: BackRequestFactory,
    ) -> dict[ViewName, ProviderResult]:
        front_result, side_result = await asyncio.gather(
            self.run_view(generation_set, front_request),
            self.run_view(generation_set, side_request),
        )

        outputs: dict[ViewName, ProviderResult] = {}
        if front_result is not None:
            outputs[ViewName.FRONT] = front_result
        if side_result is not None:
            outputs[ViewName.SIDE] = side_result

        if front_result is None or side_result is None:
            return outputs

        back_request = back_request_factory(front_result, side_result)
        back_result = await self.run_view(generation_set, back_request)
        if back_result is not None:
            outputs[ViewName.BACK] = back_result
        return outputs

    async def run_view(
        self,
        generation_set: GenerationSet,
        request: GenerationRequest,
    ) -> ProviderResult | None:
        attempt = generation_set.start_attempt(request.view)
        if request.attempt != attempt.number:
            generation_set.fail_view(request.view, ProviderErrorCode.TECHNICAL_FAILURE.value)
            raise InvalidViewTransition(
                f"{request.view.value} request attempt {request.attempt} does not match "
                f"domain attempt {attempt.number}"
            )

        try:
            result = await asyncio.wait_for(
                self._provider.generate(request),
                timeout=self._call_timeout_seconds,
            )
        except TimeoutError:
            generation_set.fail_view(request.view, ProviderErrorCode.TIMEOUT.value)
            return None
        except ProviderError as error:
            generation_set.fail_view(request.view, error.code.value)
            return None
        except asyncio.CancelledError:
            generation_set.cancel_view(request.view)
            raise

        result_id = result.request_id
        if self._result_sink is not None:
            try:
                result_id = await self._result_sink(request, result)
            except Exception:
                generation_set.fail_view(
                    request.view,
                    ProviderErrorCode.TECHNICAL_FAILURE.value,
                )
                return None

        generation_set.succeed_view(request.view, result_id)
        return result
