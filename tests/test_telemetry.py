from __future__ import annotations

import json
from dataclasses import replace

import pytest


def _event(*, attempt: int, status: str = "succeeded"):
    from hair_tryon.telemetry import EstimatedCost, TelemetryEvent

    return TelemetryEvent(
        event_type="provider_call_finished",
        provider_mode="gemini",
        attempt=attempt,
        elapsed_ms=100 * attempt,
        status=status,
        error_code=None,
        usage={"output_images": 1},
        estimated_cost=EstimatedCost(
            amount_microunits=10,
            currency="USD",
            pricing_version="2026-08-04",
        ),
    )


def test_event_log_persists_required_call_fields_as_one_json_line(tmp_path) -> None:
    from hair_tryon.telemetry import EstimatedCost, EventLog, TelemetryEvent

    log_path = tmp_path / "events.jsonl"
    log = EventLog(log_path)
    event = TelemetryEvent(
        event_type="provider_call_finished",
        provider_mode="gemini",
        attempt=2,
        elapsed_ms=1234,
        status="failed",
        error_code="timeout",
        usage={"input_tokens": 17, "output_tokens": 0},
        estimated_cost=EstimatedCost(
            amount_microunits=25,
            currency="USD",
            pricing_version="2026-08-04",
        ),
    )

    log.append(event)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["provider_mode"] == "gemini"
    assert record["attempt"] == 2
    assert record["elapsed_ms"] == 1234
    assert record["error_code"] == "timeout"
    assert record["usage"] == {"input_tokens": 17, "output_tokens": 0}
    assert record["estimated_cost"] == {
        "amount_microunits": 25,
        "currency": "USD",
        "is_estimate": True,
        "pricing_version": "2026-08-04",
    }


def test_event_log_persists_model_and_slow_call_metadata_at_top_level(tmp_path) -> None:
    from hair_tryon.telemetry import EstimatedCost, EventLog, TelemetryEvent

    log_path = tmp_path / "events.jsonl"
    EventLog(log_path).append(
        TelemetryEvent(
            event_type="provider_call_finished",
            provider_mode="nano_banana",
            attempt=1,
            elapsed_ms=16_000,
            status="succeeded",
            error_code=None,
            usage={"totalTokenCount": 17},
            estimated_cost=EstimatedCost(150_000, "CNY", "2026-08-04"),
            model_id="gemini-3.1-flash-image-preview",
            variant="standard",
            slow_call=True,
            request_id="response-1",
            http_status=200,
        )
    )

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record["model_id"] == "gemini-3.1-flash-image-preview"
    assert record["variant"] == "standard"
    assert record["slow_call"] is True
    assert record["request_id"] == "response-1"
    assert record["http_status"] == 200


def test_event_log_appends_without_rewriting_existing_events(tmp_path) -> None:
    from hair_tryon.telemetry import EventLog

    log_path = tmp_path / "events.jsonl"
    log = EventLog(log_path)
    log.append(_event(attempt=1))
    original_line = log_path.read_text(encoding="utf-8").splitlines()[0]

    log.append(_event(attempt=2, status="failed"))

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == original_line
    assert json.loads(lines[1])["attempt"] == 2


@pytest.mark.parametrize(
    "unsafe_usage",
    [
        {"image_bytes": b"private-image-content"},
        {"image_base64": "cHJpdmF0ZS1pbWFnZS1jb250ZW50"},
        {"image_url": "https://images.example.invalid/long-lived/result.png"},
    ],
)
def test_event_log_rejects_image_content_base64_and_urls(
    tmp_path,
    unsafe_usage,
) -> None:
    from hair_tryon.telemetry import EventLog, SensitiveTelemetryDataError

    log_path = tmp_path / "events.jsonl"
    log = EventLog(log_path)

    with pytest.raises(SensitiveTelemetryDataError):
        log.append(replace(_event(attempt=1), usage=unsafe_usage))

    assert not log_path.exists()


def test_raw_integer_report_fails_when_any_event_uses_fake_provider(tmp_path) -> None:
    from hair_tryon.telemetry import EventLog, FakeProviderReportError

    log = EventLog(tmp_path / "events.jsonl")
    log.append(_event(attempt=1))
    log.append(replace(_event(attempt=1), provider_mode="fake"))

    with pytest.raises(FakeProviderReportError):
        log.build_raw_integer_report()


def test_raw_integer_report_contains_only_hand_checked_call_counts(tmp_path) -> None:
    from hair_tryon.telemetry import EventLog

    log = EventLog(tmp_path / "events.jsonl")
    log.append(_event(attempt=1, status="succeeded"))
    log.append(
        replace(
            _event(attempt=2, status="failed"),
            elapsed_ms=250,
            error_code="timeout",
        )
    )
    log.append(
        replace(
            _event(attempt=1, status="cancelled"),
            elapsed_ms=50,
            error_code="cancelled",
            estimated_cost=None,
        )
    )

    report = log.build_raw_integer_report()

    assert report == {
        "provider_calls": 3,
        "retries": 1,
        "succeeded": 1,
        "failed": 1,
        "cancelled": 1,
        "timeouts": 1,
        "technical_failures": 0,
        "total_elapsed_ms": 400,
        "estimated_cost_microunits": 20,
    }
    assert all(type(value) is int for value in report.values())


def test_formal_report_keeps_locked_model_metadata_outside_integer_counts(
    tmp_path,
) -> None:
    from hair_tryon.telemetry import EventLog

    log = EventLog(tmp_path / "events.jsonl")
    event = replace(
        _event(attempt=1),
        provider_mode="nano_banana",
        model_id="gemini-3.1-flash-image-preview",
        variant="standard",
    )
    log.append(event)

    report = log.build_formal_report()

    assert report["model_id"] == "gemini-3.1-flash-image-preview"
    assert report["variant"] == "standard"
    assert report["counts"]["provider_calls"] == 1
    assert all(type(value) is int for value in report["counts"].values())
