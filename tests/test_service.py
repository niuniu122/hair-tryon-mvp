from __future__ import annotations

import hashlib
import io
import json
import asyncio

import pytest
from PIL import Image

from hair_tryon.capture_quality import CaptureKind, CaptureMetadata
from hair_tryon.domain import ViewName
from hair_tryon.providers import FakeProvider, GenerationRequest, ProviderResult
from hair_tryon.storage import TempImageStore
from hair_tryon.telemetry import EventLog


class RecordingValidator:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, CaptureKind]] = []

    def validate(
        self,
        data: bytes,
        mime_type: str,
        expected_kind: CaptureKind,
    ) -> CaptureMetadata:
        self.calls.append((data, mime_type, expected_kind))
        return CaptureMetadata(
            width=640,
            height=640,
            mime_type=mime_type,
            sha256=hashlib.sha256(data).hexdigest(),
        )


def jpeg_with_private_exif() -> bytes:
    image = Image.new("RGB", (640, 640), "white")
    exif = Image.Exif()
    exif[270] = "private camera note"
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def png_bytes(color: str = "blue") -> bytes:
    image = Image.new("RGB", (32, 32), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def wait_for_state(service, session_id: str, generation_set_id: str, state: str):
    for _ in range(200):
        status = service.generation_set_status(session_id, generation_set_id)
        if status["state"] == state:
            return status
        await asyncio.sleep(0)
    raise AssertionError(f"generation set did not reach {state}")


async def wait_for_view_attempt(
    service,
    session_id: str,
    generation_set_id: str,
    view: str,
    attempt: int,
):
    for _ in range(200):
        status = service.generation_set_status(session_id, generation_set_id)
        view_status = status["views"][view]
        if view_status["attempt"] == attempt and view_status["state"] != "running":
            return status
        await asyncio.sleep(0)
    raise AssertionError(f"{view} did not finish attempt {attempt}")


def add_required_captures(service, session_id: str) -> None:
    source = jpeg_with_private_exif()
    service.add_capture(session_id, CaptureKind.FRONT, source, "image/jpeg")
    service.add_capture(
        session_id,
        CaptureKind.SUBJECT_RIGHT_PROFILE,
        source,
        "image/jpeg",
    )


def make_service(
    tmp_path,
    *,
    validator=None,
    provider=None,
    clock=None,
    image_store=None,
):
    from hair_tryon.service import HairTryOnService

    return HairTryOnService(
        provider=provider or FakeProvider(),
        provider_mode="fake",
        image_store=image_store or TempImageStore(tmp_path / "images"),
        event_log=EventLog(tmp_path / "events.jsonl"),
        capture_validator=validator or RecordingValidator(),
        clock=clock,
    )


def test_catalog_is_frozen_to_the_five_approved_hairstyles(tmp_path) -> None:
    service = make_service(tmp_path)

    assert service.catalog() == [
        {"id": "H01", "name": "Buzz Cut"},
        {"id": "H02", "name": "Crew Cut"},
        {"id": "H03", "name": "French Crop"},
        {"id": "H04", "name": "Side Part"},
        {"id": "H05", "name": "Short Quiff"},
    ]


@pytest.mark.parametrize(
    ("participant_id", "explicit_consent", "expected_code"),
    [
        ("T00", True, "participant_not_registered"),
        ("T01", False, "explicit_consent_required"),
    ],
)
def test_session_requires_registered_participant_and_explicit_consent(
    tmp_path,
    participant_id,
    explicit_consent,
    expected_code,
) -> None:
    from hair_tryon.service import ServiceError

    service = make_service(tmp_path)

    with pytest.raises(ServiceError) as error:
        service.create_session(participant_id, explicit_consent=explicit_consent)

    assert error.value.code == expected_code


def test_only_one_session_can_be_active(tmp_path) -> None:
    from hair_tryon.service import ServiceError

    service = make_service(tmp_path)
    first = service.create_session("T01", explicit_consent=True)

    with pytest.raises(ServiceError) as error:
        service.create_session("T02", explicit_consent=True)

    assert first["session_id"]
    assert error.value.code == "active_session_exists"


def test_capture_is_validated_then_sanitized_and_stored_by_opaque_id(tmp_path) -> None:
    validator = RecordingValidator()
    service = make_service(tmp_path, validator=validator)
    session = service.create_session("T01", explicit_consent=True)
    source = jpeg_with_private_exif()

    capture = service.add_capture(
        session["session_id"],
        CaptureKind.FRONT,
        source,
        "image/jpeg",
    )

    assert validator.calls == [(source, "image/jpeg", CaptureKind.FRONT)]
    assert capture["image_id"]
    assert "/" not in capture["image_id"]
    assert "\\" not in capture["image_id"]
    stored = service.read_image(session["session_id"], capture["image_id"])
    with Image.open(io.BytesIO(stored.data)) as image:
        assert dict(image.getexif()) == {}


class PartialGenerationProvider:
    def __init__(self) -> None:
        self.calls: list[GenerationRequest] = []
        self.front_returned = asyncio.Event()
        self.release_side = asyncio.Event()

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        self.calls.append(request)
        if request.view is ViewName.FRONT:
            self.front_returned.set()
        elif request.view is ViewName.SIDE:
            await self.release_side.wait()
        return ProviderResult(
            provider_mode="fake",
            model="fake-deterministic",
            image_bytes=png_bytes(
                {
                    ViewName.FRONT: "blue",
                    ViewName.SIDE: "green",
                    ViewName.BACK: "red",
                }[request.view]
            ),
            mime_type="image/png",
            request_id=f"{request.view.value}-{request.attempt}",
            is_fake=True,
            usage={"output_images": 1},
        )


@pytest.mark.asyncio
async def test_generation_is_idempotent_and_exposes_each_persisted_result(tmp_path) -> None:
    provider = PartialGenerationProvider()
    service = make_service(tmp_path, provider=provider)
    session_id = service.create_session("T01", explicit_consent=True)["session_id"]
    add_required_captures(service, session_id)

    created = await service.create_generation_set(
        session_id,
        idempotency_key="request-1",
        hairstyle_id="H01",
    )
    duplicate = await service.create_generation_set(
        session_id,
        idempotency_key="request-1",
        hairstyle_id="H01",
    )
    await provider.front_returned.wait()
    partial = await wait_for_state(
        service,
        session_id,
        created["generation_set_id"],
        "partial_ready",
    )

    assert duplicate["generation_set_id"] == created["generation_set_id"]
    assert partial["views"]["front"]["result_id"]
    assert partial["views"]["front"]["is_fake"] is True
    assert partial["views"]["side"]["state"] == "running"
    front_image = service.read_image(
        session_id,
        partial["views"]["front"]["result_id"],
    )
    assert front_image.mime_type == "image/png"

    provider.release_side.set()
    complete = await wait_for_state(
        service,
        session_id,
        created["generation_set_id"],
        "three_views_ready",
    )

    assert {request.view for request in provider.calls[:2]} == {
        ViewName.FRONT,
        ViewName.SIDE,
    }
    assert provider.calls[2].view is ViewName.BACK
    assert all(view["result_id"] for view in complete["views"].values())
    records = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 3
    assert all(record["provider_mode"] == "fake" for record in records)
    assert all("usage" in record and "estimated_cost" in record for record in records)


@pytest.mark.asyncio
async def test_model_can_change_before_first_generation_then_locks(tmp_path) -> None:
    from hair_tryon.providers import NanoBananaProvider
    from hair_tryon.service import ServiceError

    service = make_service(tmp_path, provider=ImmediateProvider())
    created_session = service.create_session("T01", explicit_consent=True)
    session_id = created_session["session_id"]
    assert created_session["model_id"] == NanoBananaProvider.DEFAULT_MODEL
    assert created_session["model_locked"] is False

    selected = service.select_model(
        session_id,
        "gemini-3-pro-image-preview",
    )
    assert selected["model_id"] == "gemini-3-pro-image-preview"
    assert selected["model_locked"] is False
    add_required_captures(service, session_id)
    generated = await service.create_generation_set(
        session_id,
        idempotency_key="request-1",
        hairstyle_id="H01",
    )
    assert generated["model_id"] == "gemini-3-pro-image-preview"
    assert generated["variant"] == "standard"
    assert generated["model_locked"] is True

    with pytest.raises(ServiceError) as error:
        service.select_model(session_id, NanoBananaProvider.DEFAULT_MODEL)
    assert error.value.code == "model_locked"


class ImmediateProvider:
    def __init__(self) -> None:
        self.calls: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        self.calls.append(request)
        return ProviderResult(
            provider_mode="fake",
            model="fake-deterministic",
            image_bytes=png_bytes(),
            mime_type="image/png",
            request_id=f"{request.view.value}-{request.attempt}",
            is_fake=True,
            usage={"output_images": 1},
        )


@pytest.mark.asyncio
async def test_manual_retry_uses_attempt_two_as_final_and_rejects_a_third(tmp_path) -> None:
    from hair_tryon.service import ServiceError

    provider = ImmediateProvider()
    service = make_service(tmp_path, provider=provider)
    session_id = service.create_session("T01", explicit_consent=True)["session_id"]
    add_required_captures(service, session_id)
    created = await service.create_generation_set(
        session_id,
        idempotency_key="request-1",
        hairstyle_id="H01",
    )
    generation_set_id = created["generation_set_id"]
    await wait_for_state(service, session_id, generation_set_id, "three_views_ready")

    await service.retry_view(session_id, generation_set_id, ViewName.FRONT)
    retried = await wait_for_view_attempt(
        service,
        session_id,
        generation_set_id,
        "front",
        2,
    )

    assert retried["views"]["front"]["result_id"] != created["views"]["front"]["result_id"]
    assert [
        request.attempt for request in provider.calls if request.view is ViewName.FRONT
    ] == [1, 2]
    with pytest.raises(ServiceError) as error:
        await service.retry_view(session_id, generation_set_id, ViewName.FRONT)
    assert error.value.code == "attempt_limit_exceeded"


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_end_session_cancels_tasks_revokes_images_and_allows_next_session(
    tmp_path,
) -> None:
    from hair_tryon.service import ServiceError

    provider = BlockingProvider()
    service = make_service(tmp_path, provider=provider)
    session_id = service.create_session("T01", explicit_consent=True)["session_id"]
    add_required_captures(service, session_id)
    created = await service.create_generation_set(
        session_id,
        idempotency_key="request-1",
        hairstyle_id="H01",
    )
    await provider.started.wait()
    capture_id = next(
        value["image_id"]
        for value in [
            service.add_capture(
                session_id,
                CaptureKind.FRONT,
                jpeg_with_private_exif(),
                "image/jpeg",
            )
        ]
    )

    ended = await service.end_session(session_id)

    assert ended["state"] == "ended"
    assert ended["storage_state"] == "deleted"
    with pytest.raises(ServiceError) as error:
        service.read_image(session_id, capture_id)
    assert error.value.code == "session_ended"
    replacement = service.create_session("T02", explicit_consent=True)
    assert replacement["session_id"] != session_id
    assert created["generation_set_id"]


@pytest.mark.asyncio
async def test_end_session_runs_bounded_deletion_retries_after_transient_failure(
    tmp_path,
) -> None:
    delete_calls = 0

    def fail_once_then_delete(path) -> None:
        nonlocal delete_calls
        delete_calls += 1
        if delete_calls == 1:
            raise OSError("file is temporarily busy")
        path.rmdir()

    image_store = TempImageStore(
        tmp_path / "images",
        delete_tree=fail_once_then_delete,
    )
    service = make_service(tmp_path, image_store=image_store)
    session_id = service.create_session("T01", explicit_consent=True)["session_id"]

    ended = await service.end_session(session_id)

    assert ended["storage_state"] == "deleted"
    assert delete_calls == 2
