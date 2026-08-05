from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from hair_tryon.capture_quality import CaptureKind, CaptureValidator, sanitize_image
from hair_tryon.catalog import HAIRSTYLES, Hairstyle, get_hairstyle
from hair_tryon.domain import GenerationSet, Session, SessionState, ViewName
from hair_tryon.orchestration import GenerationOrchestrator
from hair_tryon.prompts import PROMPT_VERSION, build_prompt
from hair_tryon.providers import (
    GenerationRequest,
    ImageProvider,
    NanoBananaProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderErrorCode,
    ProviderImage,
    ProviderResult,
)
from hair_tryon.storage import StorageSessionState, TempImageStore
from hair_tryon.telemetry import EstimatedCost, EventLog, TelemetryEvent


REGISTERED_PARTICIPANTS = frozenset({"T01", "T02", "T03", "T04", "T05"})


class ServiceError(RuntimeError):
    def __init__(self, code: str, *, status_code: int = 400) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ImagePayload:
    data: bytes
    mime_type: str


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    kind: CaptureKind
    image_id: str
    sha256: str
    mime_type: str


@dataclass
class _SessionContext:
    domain: Session
    participant_id: str
    model_id: str = NanoBananaProvider.DEFAULT_MODEL
    variant: str = NanoBananaProvider.VARIANT
    model_locked: bool = False
    logged_provider: _TelemetryProvider | None = None
    captures: dict[CaptureKind, CaptureRecord] = field(default_factory=dict)
    mime_types: dict[str, str] = field(default_factory=dict)
    generation_sets: dict[str, _GenerationContext] = field(default_factory=dict)
    idempotency_keys: dict[str, str] = field(default_factory=dict)


@dataclass
class _GenerationContext:
    domain: GenerationSet
    hairstyle: Hairstyle
    model_id: str
    variant: str
    task: asyncio.Task[None] | None = None
    result_is_fake: dict[ViewName, bool] = field(default_factory=dict)


class _TelemetryProvider:
    def __init__(
        self,
        provider: ImageProvider | None,
        *,
        configured_mode: str,
        event_log: EventLog,
        clock: Callable[[], float],
        model_id: str,
        variant: str,
    ) -> None:
        self._provider = provider
        self._configured_mode = configured_mode
        self._event_log = event_log
        self._clock = clock
        self._model_id = model_id
        self._variant = variant

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        started = self._clock()
        try:
            result = await self._provider.generate(request)
        except asyncio.CancelledError:
            self._record(
                request,
                started=started,
                provider_mode=self._configured_mode,
                status="cancelled",
                error_code="cancelled",
                usage={},
            )
            raise
        except ProviderError as error:
            self._record(
                request,
                started=started,
                provider_mode=self._configured_mode,
                status="failed",
                error_code=error.code.value,
                usage={},
                request_id=error.request_id,
                http_status=error.http_status,
            )
            raise
        except Exception as error:
            self._record(
                request,
                started=started,
                provider_mode=self._configured_mode,
                status="failed",
                error_code=ProviderErrorCode.TECHNICAL_FAILURE.value,
                usage={},
            )
            raise ProviderError(ProviderErrorCode.TECHNICAL_FAILURE) from error

        self._record(
            request,
            started=started,
            provider_mode=result.provider_mode,
            status="succeeded",
            error_code=None,
            usage=result.usage,
            model_id=result.model,
            variant=result.variant,
            slow_call=result.slow_call,
            request_id=result.request_id,
            http_status=result.http_status,
            elapsed_ms=result.elapsed_ms or None,
        )
        return result

    def _record(
        self,
        request: GenerationRequest,
        *,
        started: float,
        provider_mode: str,
        status: str,
        error_code: str | None,
        usage: dict[str, Any],
        model_id: str | None = None,
        variant: str | None = None,
        slow_call: bool | None = None,
        request_id: str | None = None,
        http_status: int | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        measured_elapsed_ms = max(0, round((self._clock() - started) * 1000))
        resolved_elapsed_ms = measured_elapsed_ms if elapsed_ms is None else elapsed_ms
        resolved_slow_call = (
            resolved_elapsed_ms >= 15_000 if slow_call is None else slow_call
        )
        self._event_log.append(
            TelemetryEvent(
                event_type="provider_call_finished",
                provider_mode=provider_mode,
                attempt=request.attempt,
                elapsed_ms=resolved_elapsed_ms,
                status=status,
                error_code=error_code,
                usage=usage,
                estimated_cost=EstimatedCost(
                    amount_microunits=(
                        150_000
                        if provider_mode == "nano_banana" and status == "succeeded"
                        else 0
                    ),
                    currency="CNY",
                    pricing_version="nano-banana-standard-2026-08-04",
                ),
                model_id=model_id or self._model_id,
                variant=variant or self._variant,
                slow_call=resolved_slow_call,
                request_id=request_id,
                http_status=http_status,
            )
        )


class HairTryOnService:
    def __init__(
        self,
        *,
        provider: ImageProvider,
        provider_mode: str,
        image_store: TempImageStore,
        event_log: EventLog,
        capture_validator: CaptureValidator,
        clock: Callable[[], float] | None = None,
        provider_factory: Callable[[str], ImageProvider] | None = None,
    ) -> None:
        self._provider = provider
        self.provider_mode = provider_mode
        self._image_store = image_store
        self._event_log = event_log
        self._capture_validator = capture_validator
        self._clock = clock or time.monotonic
        self._provider_factory = provider_factory
        self._sessions: dict[str, _SessionContext] = {}
        self._active_session_id: str | None = None

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"id": style.hairstyle_id, "name": style.name}
            for style in HAIRSTYLES
        ]

    def create_session(
        self,
        participant_id: str,
        *,
        explicit_consent: bool,
    ) -> dict[str, Any]:
        if participant_id not in REGISTERED_PARTICIPANTS:
            raise ServiceError("participant_not_registered", status_code=422)
        if not explicit_consent:
            raise ServiceError("explicit_consent_required", status_code=422)
        if self._active_session_id is not None:
            active = self._sessions[self._active_session_id]
            if active.domain.state is SessionState.ACTIVE:
                raise ServiceError("active_session_exists", status_code=409)

        session_id = uuid4().hex
        domain_session = Session(session_id)
        self._image_store.create_session(session_id)
        self._sessions[session_id] = _SessionContext(
            domain=domain_session,
            participant_id=participant_id,
        )
        self._active_session_id = session_id
        return {
            "session_id": session_id,
            "participant_id": participant_id,
            "state": domain_session.state.value,
            "provider_mode": self.provider_mode,
            "model_id": NanoBananaProvider.DEFAULT_MODEL,
            "variant": NanoBananaProvider.VARIANT,
            "model_locked": False,
            "fake_warning": (
                "FAKE - NOT MODEL OUTPUT" if self.provider_mode == "fake" else None
            ),
        }

    def select_model(self, session_id: str, model_id: str) -> dict[str, Any]:
        session = self._active_session(session_id)
        if model_id not in NanoBananaProvider.ALLOWED_MODELS:
            raise ServiceError("model_not_approved", status_code=422)
        if session.model_locked:
            raise ServiceError("model_locked", status_code=409)
        session.model_id = model_id
        return {
            "session_id": session_id,
            "model_id": session.model_id,
            "variant": session.variant,
            "model_locked": session.model_locked,
        }

    def add_capture(
        self,
        session_id: str,
        kind: CaptureKind,
        data: bytes,
        mime_type: str,
    ) -> dict[str, str]:
        session = self._active_session(session_id)
        self._capture_validator.validate(data, mime_type, kind)
        sanitized = sanitize_image(data, mime_type)
        stored = self._image_store.save_image(session_id, sanitized)
        record = CaptureRecord(
            kind=kind,
            image_id=stored.image_id,
            sha256=stored.sha256,
            mime_type=mime_type,
        )
        session.captures[kind] = record
        session.mime_types[stored.image_id] = mime_type
        return {
            "kind": kind.value,
            "image_id": stored.image_id,
            "sha256": stored.sha256,
        }

    def read_image(self, session_id: str, image_id: str) -> ImagePayload:
        session = self._active_session(session_id)
        mime_type = session.mime_types.get(image_id)
        if mime_type is None:
            raise ServiceError("image_not_found", status_code=404)
        try:
            data = self._image_store.read_image(session_id, image_id)
        except (KeyError, FileNotFoundError):
            raise ServiceError("image_not_found", status_code=404) from None
        return ImagePayload(data=data, mime_type=mime_type)

    async def create_generation_set(
        self,
        session_id: str,
        *,
        idempotency_key: str,
        hairstyle_id: str,
    ) -> dict[str, Any]:
        session = self._active_session(session_id)
        existing_id = session.idempotency_keys.get(idempotency_key)
        if existing_id is not None:
            existing = session.generation_sets[existing_id]
            if existing.hairstyle.hairstyle_id != hairstyle_id:
                raise ServiceError("idempotency_conflict", status_code=409)
            return self.generation_set_status(session_id, existing_id)

        hairstyle = get_hairstyle(hairstyle_id)
        if hairstyle is None:
            raise ServiceError("hairstyle_not_found", status_code=404)
        required = {CaptureKind.FRONT, CaptureKind.SUBJECT_RIGHT_PROFILE}
        if not required.issubset(session.captures):
            raise ServiceError("captures_incomplete", status_code=409)

        if not session.model_locked:
            try:
                provider = (
                    self._provider_factory(session.model_id)
                    if self._provider_factory is not None
                    else self._provider
                )
            except ProviderConfigurationError:
                raise ServiceError("provider_not_configured", status_code=503) from None
            if provider is None:
                raise ServiceError("provider_not_configured", status_code=503)
            session.logged_provider = _TelemetryProvider(
                provider,
                configured_mode=self.provider_mode,
                event_log=self._event_log,
                clock=self._clock,
                model_id=session.model_id,
                variant=session.variant,
            )
            session.model_locked = True

        generation_set_id = uuid4().hex
        domain_set = session.domain.create_generation_set(
            generation_set_id,
            hairstyle_id,
        )
        context = _GenerationContext(
            domain=domain_set,
            hairstyle=hairstyle,
            model_id=session.model_id,
            variant=session.variant,
        )
        session.generation_sets[generation_set_id] = context
        session.idempotency_keys[idempotency_key] = generation_set_id
        context.task = asyncio.create_task(
            self._run_initial(session_id, session, context)
        )
        context.task.add_done_callback(self._consume_task_result)
        return self.generation_set_status(session_id, generation_set_id)

    def generation_set_status(
        self,
        session_id: str,
        generation_set_id: str,
    ) -> dict[str, Any]:
        session = self._active_session(session_id)
        context = session.generation_sets.get(generation_set_id)
        if context is None:
            raise ServiceError("generation_set_not_found", status_code=404)
        return {
            "generation_set_id": generation_set_id,
            "hairstyle_id": context.hairstyle.hairstyle_id,
            "state": context.domain.state.value,
            "provider_mode": self.provider_mode,
            "model_id": context.model_id,
            "variant": context.variant,
            "model_locked": session.model_locked,
            "fake_warning": (
                "FAKE - NOT MODEL OUTPUT" if self.provider_mode == "fake" else None
            ),
            "views": {
                view.value: self._view_status(context, view) for view in ViewName
            },
        }

    async def retry_view(
        self,
        session_id: str,
        generation_set_id: str,
        view: ViewName,
    ) -> dict[str, Any]:
        session = self._active_session(session_id)
        context = session.generation_sets.get(generation_set_id)
        if context is None:
            raise ServiceError("generation_set_not_found", status_code=404)
        if context.task is not None and not context.task.done():
            raise ServiceError("generation_in_progress", status_code=409)
        view_record = context.domain.view(view)
        if not view_record.attempts:
            raise ServiceError("view_not_attempted", status_code=409)
        if len(view_record.attempts) >= 2:
            raise ServiceError("attempt_limit_exceeded", status_code=409)

        context.task = asyncio.create_task(
            self._run_retry(session_id, session, context, view)
        )
        context.task.add_done_callback(self._consume_task_result)
        return self.generation_set_status(session_id, generation_set_id)

    async def end_session(self, session_id: str) -> dict[str, str]:
        session = self._active_session(session_id)
        session.domain.end()
        tasks = [
            context.task
            for context in session.generation_sets.values()
            if context.task is not None and not context.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        storage_state = self._image_store.end_session(session_id)
        for _ in range(self._image_store.MAX_DELETION_RETRIES):
            if storage_state is not StorageSessionState.DELETION_PENDING:
                break
            await asyncio.sleep(0)
            storage_state = self._image_store.retry_deletion(session_id)
        return {
            "session_id": session_id,
            "state": session.domain.state.value,
            "storage_state": storage_state.value,
        }

    async def _run_initial(
        self,
        session_id: str,
        session: _SessionContext,
        context: _GenerationContext,
    ) -> None:
        orchestrator = self._orchestrator(session_id, session, context)
        await orchestrator.run_initial(
            context.domain,
            front_request=self._capture_request(
                session_id,
                session,
                context,
                ViewName.FRONT,
                1,
            ),
            side_request=self._capture_request(
                session_id,
                session,
                context,
                ViewName.SIDE,
                1,
            ),
            back_request_factory=lambda front, side: self._back_request(
                session_id,
                session,
                context,
                front,
                side,
                1,
            ),
        )

    async def _run_retry(
        self,
        session_id: str,
        session: _SessionContext,
        context: _GenerationContext,
        view: ViewName,
    ) -> None:
        orchestrator = self._orchestrator(session_id, session, context)
        if view is ViewName.BACK:
            request = self._back_request_from_storage(
                session_id,
                session,
                context,
                attempt=2,
            )
        else:
            request = self._capture_request(
                session_id,
                session,
                context,
                view,
                2,
            )
        await orchestrator.run_view(context.domain, request)

    def _orchestrator(
        self,
        session_id: str,
        session: _SessionContext,
        context: _GenerationContext,
    ) -> GenerationOrchestrator:
        async def persist(
            request: GenerationRequest,
            result: ProviderResult,
        ) -> str:
            if session.domain.state is not SessionState.ACTIVE:
                raise ServiceError("session_ended", status_code=410)
            stored = self._image_store.save_image(session_id, result.image_bytes)
            session.mime_types[stored.image_id] = result.mime_type
            context.result_is_fake[request.view] = result.is_fake
            return stored.image_id

        if session.logged_provider is None:
            raise ServiceError("provider_not_configured", status_code=503)
        return GenerationOrchestrator(
            session.logged_provider,
            call_timeout_seconds=65.0,
            result_sink=persist,
        )

    def _capture_request(
        self,
        session_id: str,
        session: _SessionContext,
        context: _GenerationContext,
        view: ViewName,
        attempt: int,
    ) -> GenerationRequest:
        capture_kind = (
            CaptureKind.FRONT
            if view is ViewName.FRONT
            else CaptureKind.SUBJECT_RIGHT_PROFILE
        )
        capture = session.captures[capture_kind]
        return GenerationRequest(
            generation_set_id=context.domain.generation_set_id,
            view=view,
            attempt=attempt,
            prompt=build_prompt(context.hairstyle, view),
            prompt_version=PROMPT_VERSION,
            images=(
                ProviderImage(
                    role=f"{view.value}_capture",
                    mime_type=capture.mime_type,
                    data=self._image_store.read_image(session_id, capture.image_id),
                ),
            ),
        )

    def _back_request(
        self,
        session_id: str,
        session: _SessionContext,
        context: _GenerationContext,
        front: ProviderResult,
        side: ProviderResult,
        attempt: int,
    ) -> GenerationRequest:
        captures = tuple(
            ProviderImage(
                role=f"{kind.value}_capture",
                mime_type=session.captures[kind].mime_type,
                data=self._image_store.read_image(
                    session_id,
                    session.captures[kind].image_id,
                ),
            )
            for kind in (CaptureKind.FRONT, CaptureKind.SUBJECT_RIGHT_PROFILE)
        )
        return GenerationRequest(
            generation_set_id=context.domain.generation_set_id,
            view=ViewName.BACK,
            attempt=attempt,
            prompt=build_prompt(context.hairstyle, ViewName.BACK),
            prompt_version=PROMPT_VERSION,
            images=captures
            + (
                ProviderImage("generated_front", front.mime_type, front.image_bytes),
                ProviderImage("generated_side", side.mime_type, side.image_bytes),
            ),
        )

    def _back_request_from_storage(
        self,
        session_id: str,
        session: _SessionContext,
        context: _GenerationContext,
        *,
        attempt: int,
    ) -> GenerationRequest:
        generated_images: list[ProviderImage] = []
        for view in (ViewName.FRONT, ViewName.SIDE):
            result_id = context.domain.view(view).final_attempt.result_id
            if result_id is None:
                raise ServiceError("back_dependencies_missing", status_code=409)
            generated_images.append(
                ProviderImage(
                    role=f"generated_{view.value}",
                    mime_type=session.mime_types[result_id],
                    data=self._image_store.read_image(session_id, result_id),
                )
            )
        captures = tuple(
            ProviderImage(
                role=f"{kind.value}_capture",
                mime_type=session.captures[kind].mime_type,
                data=self._image_store.read_image(
                    session_id,
                    session.captures[kind].image_id,
                ),
            )
            for kind in (CaptureKind.FRONT, CaptureKind.SUBJECT_RIGHT_PROFILE)
        )
        return GenerationRequest(
            generation_set_id=context.domain.generation_set_id,
            view=ViewName.BACK,
            attempt=attempt,
            prompt=build_prompt(context.hairstyle, ViewName.BACK),
            prompt_version=PROMPT_VERSION,
            images=captures + tuple(generated_images),
        )

    @staticmethod
    def _view_status(
        context: _GenerationContext,
        view: ViewName,
    ) -> dict[str, Any]:
        record = context.domain.view(view)
        if not record.attempts:
            return {
                "state": record.state.value,
                "attempt": 0,
                "result_id": None,
                "error_code": None,
                "is_fake": None,
            }
        attempt = record.final_attempt
        return {
            "state": attempt.state.value,
            "attempt": attempt.number,
            "result_id": attempt.result_id,
            "error_code": attempt.error_code,
            "is_fake": context.result_is_fake.get(view),
        }

    @staticmethod
    def _consume_task_result(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        task.exception()

    def _active_session(self, session_id: str) -> _SessionContext:
        session = self._sessions.get(session_id)
        if session is None:
            raise ServiceError("session_not_found", status_code=404)
        if session.domain.state is not SessionState.ACTIVE:
            raise ServiceError("session_ended", status_code=410)
        return session

    def formal_report(self) -> dict[str, Any]:
        return self._event_log.build_formal_report()
