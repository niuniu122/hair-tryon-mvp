from __future__ import annotations

import hashlib
import io
import time

from fastapi.testclient import TestClient
from PIL import Image

from hair_tryon.capture_quality import CaptureKind, CaptureMetadata
from hair_tryon.providers import FakeProvider
from hair_tryon.service import HairTryOnService
from hair_tryon.storage import TempImageStore
from hair_tryon.telemetry import EventLog


class AcceptingValidator:
    def validate(
        self,
        data: bytes,
        mime_type: str,
        expected_kind: CaptureKind,
    ) -> CaptureMetadata:
        return CaptureMetadata(
            width=640,
            height=640,
            mime_type=mime_type,
            sha256=hashlib.sha256(data).hexdigest(),
        )


def jpeg_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (640, 640), "white").save(output, format="JPEG")
    return output.getvalue()


def client(tmp_path) -> TestClient:
    from hair_tryon.app import create_app

    service = HairTryOnService(
        provider=FakeProvider(),
        provider_mode="fake",
        image_store=TempImageStore(tmp_path / "images"),
        event_log=EventLog(tmp_path / "events.jsonl"),
        capture_validator=AcceptingValidator(),
    )
    return TestClient(create_app(service=service))


def test_health_catalog_and_run_model_selection_are_explicit(tmp_path) -> None:
    with client(tmp_path) as api:
        health = api.get("/api/health")
        catalog = api.get("/api/catalog")
        created = api.post(
            "/api/sessions",
            json={"participant_id": "T01", "explicit_consent": True},
        )

        assert health.status_code == 200
        assert health.json()["provider_mode"] == "fake"
        assert health.json()["fake_warning"] == "FAKE - NOT MODEL OUTPUT"
        assert catalog.json()[0] == {"id": "H01", "name": "Buzz Cut"}
        assert len(catalog.json()) == 5
        session = created.json()
        assert session["model_id"] == "gemini-3.1-flash-image-preview"
        selected = api.put(
            f"/api/sessions/{session['session_id']}/model",
            json={"model_id": "gemini-3-pro-image-preview"},
        )
        assert selected.status_code == 200
        assert selected.json()["model_id"] == "gemini-3-pro-image-preview"


def test_index_and_static_assets_do_not_intercept_api_routes(tmp_path) -> None:
    with client(tmp_path) as api:
        index = api.get("/")
        stylesheet = api.get("/static/styles.css")
        health = api.get("/api/health")

        assert index.status_code == 200
        assert index.headers["content-type"].startswith("text/html")
        assert "<main" in index.text
        assert stylesheet.status_code == 200
        assert stylesheet.headers["content-type"].startswith("text/css")
        assert health.status_code == 200
        assert health.headers["content-type"].startswith("application/json")
        assert health.json()["status"] == "ok"


def test_api_generation_image_retry_end_and_fake_report_gate(tmp_path) -> None:
    with client(tmp_path) as api:
        session_id = api.post(
            "/api/sessions",
            json={"participant_id": "T01", "explicit_consent": True},
        ).json()["session_id"]
        source = jpeg_bytes()
        for kind in ("front", "subject_right_profile"):
            response = api.post(
                f"/api/sessions/{session_id}/captures/{kind}",
                files={"file": (f"{kind}.jpg", source, "image/jpeg")},
            )
            assert response.status_code == 201

        created = api.post(
            f"/api/sessions/{session_id}/generation-sets",
            json={"idempotency_key": "request-1", "hairstyle_id": "H01"},
        )
        assert created.status_code == 202
        generation_set_id = created.json()["generation_set_id"]

        status = None
        for _ in range(100):
            response = api.get(
                f"/api/sessions/{session_id}/generation-sets/{generation_set_id}"
            )
            status = response.json()
            if status["state"] == "three_views_ready":
                break
            time.sleep(0.01)
        assert status is not None
        assert status["state"] == "three_views_ready"
        assert status["model_locked"] is True
        front_id = status["views"]["front"]["result_id"]
        image = api.get(f"/api/sessions/{session_id}/images/{front_id}")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

        retried = api.post(
            f"/api/sessions/{session_id}/generation-sets/{generation_set_id}"
            "/views/front/retry"
        )
        assert retried.status_code == 202
        formal = api.get("/api/formal-report")
        assert formal.status_code == 409
        assert formal.json()["error"]["code"] == "fake_report_forbidden"

        ended = api.delete(f"/api/sessions/{session_id}")
        assert ended.status_code == 200
        assert ended.json()["storage_state"] == "deleted"
        assert api.get(f"/api/sessions/{session_id}/images/{front_id}").status_code == 410
