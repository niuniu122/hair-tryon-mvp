from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class TelemetryError(RuntimeError):
    """Base error for telemetry operations."""


class SensitiveTelemetryDataError(TelemetryError):
    """Raised before image content or a durable URL can enter the log."""


class FakeProviderReportError(TelemetryError):
    """Raised when fake output would enter a formal evaluation report."""


class MixedModelReportError(TelemetryError):
    """Raised when one formal run contains more than one model configuration."""


@dataclass(frozen=True, slots=True)
class EstimatedCost:
    amount_microunits: int
    currency: str
    pricing_version: str
    is_estimate: bool = True


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    event_type: str
    provider_mode: str
    attempt: int
    elapsed_ms: int
    status: str
    error_code: str | None
    usage: dict[str, Any]
    estimated_cost: EstimatedCost | None
    model_id: str | None = None
    variant: str | None = None
    slow_call: bool = False
    request_id: str | None = None
    http_status: int | None = None


class EventLog:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def append(self, event: TelemetryEvent) -> None:
        record = asdict(event)
        _reject_sensitive_data(record)
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
        with self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.write("\n")

    def build_raw_integer_report(self) -> dict[str, int]:
        records = self._read_records()
        if any(record.get("provider_mode") == "fake" for record in records):
            raise FakeProviderReportError(
                "formal raw integer reports cannot contain fake provider events"
            )
        return {
            "provider_calls": len(records),
            "retries": sum(record.get("attempt") == 2 for record in records),
            "succeeded": sum(
                record.get("status") == "succeeded" for record in records
            ),
            "failed": sum(record.get("status") == "failed" for record in records),
            "cancelled": sum(
                record.get("status") == "cancelled" for record in records
            ),
            "timeouts": sum(
                record.get("error_code") == "timeout" for record in records
            ),
            "technical_failures": sum(
                record.get("error_code") == "technical_failure"
                for record in records
            ),
            "total_elapsed_ms": sum(
                int(record.get("elapsed_ms") or 0) for record in records
            ),
            "estimated_cost_microunits": sum(
                int((record.get("estimated_cost") or {}).get("amount_microunits") or 0)
                for record in records
            ),
        }

    def build_formal_report(self) -> dict[str, Any]:
        records = self._read_records()
        counts = self.build_raw_integer_report()
        model_ids = {
            record.get("model_id") for record in records if record.get("model_id")
        }
        variants = {
            record.get("variant") for record in records if record.get("variant")
        }
        if len(model_ids) > 1 or len(variants) > 1:
            raise MixedModelReportError(
                "formal reports require one locked model and variant"
            )
        return {
            "model_id": next(iter(model_ids), None),
            "variant": next(iter(variants), None),
            "counts": counts,
        }

    def _read_records(self) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line
        ]


def _reject_sensitive_data(value: Any, *, key: str | None = None) -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise SensitiveTelemetryDataError("binary data is forbidden in telemetry")

    normalized_key = (key or "").casefold()
    if (
        "base64" in normalized_key
        or normalized_key in {"image_bytes", "image_data", "image_url", "url"}
        or normalized_key.endswith("_url")
    ):
        raise SensitiveTelemetryDataError(
            f"field {key!r} is forbidden in telemetry"
        )

    if isinstance(value, str):
        normalized_value = value.strip().casefold()
        if normalized_value.startswith(("data:image", "http://", "https://")):
            raise SensitiveTelemetryDataError(
                "image data and durable URLs are forbidden in telemetry"
            )
        return

    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            _reject_sensitive_data(child_value, key=str(child_key))
        return

    if isinstance(value, Sequence):
        for child in value:
            _reject_sensitive_data(child)
