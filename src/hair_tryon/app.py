from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hair_tryon.capture_quality import (
    CaptureKind,
    CaptureValidationError,
    CaptureValidator,
)
from hair_tryon.config import RuntimeConfig
from hair_tryon.domain import ViewName
from hair_tryon.providers import (
    FakeProvider,
    NanoBananaProvider,
    ProviderConfigurationError,
)
from hair_tryon.service import HairTryOnService, ServiceError
from hair_tryon.storage import TempImageStore
from hair_tryon.telemetry import (
    EventLog,
    FakeProviderReportError,
    MixedModelReportError,
)


class CreateSessionBody(BaseModel):
    participant_id: str
    explicit_consent: bool


class SelectModelBody(BaseModel):
    model_id: str


class CreateGenerationSetBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    hairstyle_id: str


def create_app(*, service: HairTryOnService | None = None) -> FastAPI:
    runtime_service = service or _build_service()
    app = FastAPI(title="Hair Try-on MVP", version="0.1.0")
    app.state.service = runtime_service

    @app.exception_handler(ServiceError)
    async def handle_service_error(_request: Request, error: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code}},
        )

    @app.exception_handler(CaptureValidationError)
    async def handle_capture_error(
        _request: Request,
        error: CaptureValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": error.code.value}},
        )

    @app.exception_handler(FakeProviderReportError)
    async def handle_fake_report(
        _request: Request,
        _error: FakeProviderReportError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "fake_report_forbidden"}},
        )

    @app.exception_handler(MixedModelReportError)
    async def handle_mixed_model_report(
        _request: Request,
        _error: MixedModelReportError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "mixed_model_report_forbidden"}},
        )

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "provider_mode": runtime_service.provider_mode,
            "fake_warning": (
                "FAKE - NOT MODEL OUTPUT"
                if runtime_service.provider_mode == "fake"
                else None
            ),
            "default_model_id": NanoBananaProvider.DEFAULT_MODEL,
            "allowed_model_ids": sorted(NanoBananaProvider.ALLOWED_MODELS),
        }

    @app.get("/api/catalog")
    async def catalog() -> list[dict[str, str]]:
        return runtime_service.catalog()

    @app.post("/api/sessions", status_code=201)
    async def create_session(body: CreateSessionBody) -> dict[str, object]:
        return runtime_service.create_session(
            body.participant_id,
            explicit_consent=body.explicit_consent,
        )

    @app.put("/api/sessions/{session_id}/model")
    async def select_model(
        session_id: str,
        body: SelectModelBody,
    ) -> dict[str, object]:
        return runtime_service.select_model(session_id, body.model_id)

    @app.post(
        "/api/sessions/{session_id}/captures/{kind}",
        status_code=201,
    )
    async def add_capture(
        session_id: str,
        kind: str,
        file: UploadFile,
    ) -> dict[str, str]:
        try:
            capture_kind = CaptureKind(kind)
        except ValueError:
            raise ServiceError("capture_kind_invalid", status_code=422) from None
        return runtime_service.add_capture(
            session_id,
            capture_kind,
            await file.read(),
            file.content_type or "application/octet-stream",
        )

    @app.post(
        "/api/sessions/{session_id}/generation-sets",
        status_code=202,
    )
    async def create_generation_set(
        session_id: str,
        body: CreateGenerationSetBody,
    ) -> dict[str, object]:
        return await runtime_service.create_generation_set(
            session_id,
            idempotency_key=body.idempotency_key,
            hairstyle_id=body.hairstyle_id,
        )

    @app.get("/api/sessions/{session_id}/generation-sets/{generation_set_id}")
    async def generation_set_status(
        session_id: str,
        generation_set_id: str,
    ) -> dict[str, object]:
        return runtime_service.generation_set_status(session_id, generation_set_id)

    @app.get("/api/sessions/{session_id}/images/{image_id}")
    async def image(session_id: str, image_id: str) -> Response:
        payload = runtime_service.read_image(session_id, image_id)
        return Response(content=payload.data, media_type=payload.mime_type)

    @app.post(
        "/api/sessions/{session_id}/generation-sets/{generation_set_id}"
        "/views/{view}/retry",
        status_code=202,
    )
    async def retry_view(
        session_id: str,
        generation_set_id: str,
        view: str,
    ) -> dict[str, object]:
        try:
            view_name = ViewName(view)
        except ValueError:
            raise ServiceError("view_invalid", status_code=422) from None
        return await runtime_service.retry_view(
            session_id,
            generation_set_id,
            view_name,
        )

    @app.delete("/api/sessions/{session_id}")
    async def end_session(session_id: str) -> dict[str, str]:
        return await runtime_service.end_session(session_id)

    @app.get("/api/formal-report")
    async def formal_report() -> dict[str, object]:
        return runtime_service.formal_report()

    static_root = Path(__file__).with_name("static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_root / "index.html", media_type="text/html")

    app.mount("/static", StaticFiles(directory=static_root), name="static")

    return app


def _build_service() -> HairTryOnService:
    config = RuntimeConfig.from_environment()
    runtime_root = Path(tempfile.mkdtemp(prefix="hair-tryon-mvp-"))
    if config.provider_mode == "fake":
        provider = FakeProvider()
        provider_factory = None
    else:
        provider = None
        provider_factory = lambda model_id: NanoBananaProvider(model_id=model_id)
    return HairTryOnService(
        provider=provider,
        provider_factory=provider_factory,
        provider_mode=config.provider_mode,
        image_store=TempImageStore(runtime_root / "images"),
        event_log=EventLog(runtime_root / "events.jsonl"),
        capture_validator=CaptureValidator(),
    )
