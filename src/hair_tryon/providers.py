from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

import httpx
from PIL import Image, ImageDraw, PngImagePlugin

from hair_tryon.domain import ViewName


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider cannot be configured safely."""


class ProviderErrorCode(str, Enum):
    TECHNICAL_FAILURE = "technical_failure"
    TIMEOUT = "timeout"
    SAFETY_REJECTION = "safety_rejection"
    HTTP_ERROR = "http_error"
    NO_IMAGE = "no_image"
    INVALID_RESPONSE = "invalid_response"


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str | None = None,
        *,
        http_status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        self.code = code
        self.http_status = http_status
        self.request_id = request_id
        super().__init__(message or code.value)


class FakeScenario(str, Enum):
    SUCCESS = "success"
    FAIL_FIRST = "fail_first"
    ALWAYS_FAIL = "always_fail"
    TIMEOUT = "timeout"
    SAFETY_REJECTION = "safety_rejection"


@dataclass(frozen=True)
class ProviderImage:
    role: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class GenerationRequest:
    generation_set_id: str
    view: ViewName
    attempt: int
    prompt: str
    prompt_version: str
    images: tuple[ProviderImage, ...]


@dataclass(frozen=True)
class ProviderResult:
    provider_mode: str
    model: str
    image_bytes: bytes
    mime_type: str
    request_id: str
    is_fake: bool
    usage: dict[str, Any] = field(default_factory=dict)
    variant: str = "standard"
    elapsed_ms: int = 0
    slow_call: bool = False
    http_status: int | None = None


class ImageProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> ProviderResult: ...


class FakeProvider:
    """Deterministic local provider whose output can never pose as model output."""

    def __init__(self, scenario: FakeScenario = FakeScenario.SUCCESS) -> None:
        self._scenario = scenario

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        if self._scenario is FakeScenario.ALWAYS_FAIL:
            raise ProviderError(ProviderErrorCode.TECHNICAL_FAILURE)
        if self._scenario is FakeScenario.FAIL_FIRST and request.attempt == 1:
            raise ProviderError(ProviderErrorCode.TECHNICAL_FAILURE)
        if self._scenario is FakeScenario.TIMEOUT:
            raise ProviderError(ProviderErrorCode.TIMEOUT)
        if self._scenario is FakeScenario.SAFETY_REJECTION:
            raise ProviderError(ProviderErrorCode.SAFETY_REJECTION)

        digest = self._request_digest(request)
        image_bytes = self._render_image(request, digest)
        return ProviderResult(
            provider_mode="fake",
            model="fake-deterministic",
            image_bytes=image_bytes,
            mime_type="image/png",
            request_id=f"fake-{digest[:16]}",
            is_fake=True,
        )

    @staticmethod
    def _request_digest(request: GenerationRequest) -> str:
        digest = hashlib.sha256()
        for value in (
            request.generation_set_id,
            request.view.value,
            str(request.attempt),
            request.prompt,
            request.prompt_version,
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
        for image in request.images:
            digest.update(image.role.encode("utf-8"))
            digest.update(image.mime_type.encode("ascii"))
            digest.update(image.data)
        return digest.hexdigest()

    @staticmethod
    def _render_image(request: GenerationRequest, digest: str) -> bytes:
        color = tuple(bytes.fromhex(digest[:6]))
        image = Image.new("RGB", (320, 420), color=color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((14, 14, 306, 118), fill="white")
        draw.text(
            (24, 24),
            "FAKE - NOT MODEL OUTPUT\n"
            f"{request.view.value} / attempt {request.attempt}",
            fill="black",
        )
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Comment", "FAKE - NOT MODEL OUTPUT")
        output = io.BytesIO()
        image.save(output, format="PNG", pnginfo=metadata)
        return output.getvalue()


class GeminiProvider:
    """Narrow adapter for the single approved Gemini image model."""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
    MODEL = "gemini-3.1-flash-image"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        resolved_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv(
            "GOOGLE_API_KEY"
        )
        if not resolved_key or not resolved_key.strip():
            raise ProviderConfigurationError("Gemini API key is required")
        self._api_key = resolved_key
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        payload = self._build_payload(request)
        try:
            response = await self._post(payload)
        except httpx.TimeoutException as error:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from error
        except httpx.HTTPError as error:
            raise ProviderError(ProviderErrorCode.TECHNICAL_FAILURE) from error

        if not response.is_success:
            raise ProviderError(
                ProviderErrorCode.HTTP_ERROR,
                f"Gemini returned HTTP {response.status_code}",
            )

        try:
            body = response.json()
        except ValueError as error:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from error

        output = self._final_output_image(body)
        if not isinstance(output, dict) or not output.get("data"):
            raise ProviderError(ProviderErrorCode.NO_IMAGE)

        try:
            image_bytes = base64.b64decode(output["data"], validate=True)
        except (binascii.Error, TypeError, ValueError) as error:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from error

        usage = body.get("usage") or body.get("usage_metadata") or {}
        if not isinstance(usage, dict):
            usage = {}
        request_id = str(
            body.get("id")
            or response.headers.get("x-request-id")
            or response.headers.get("x-goog-request-id")
            or "unknown"
        )
        mime_type = str(output.get("mime_type") or output.get("mimeType") or "image/jpeg")
        return ProviderResult(
            provider_mode="gemini",
            model=self.MODEL,
            image_bytes=image_bytes,
            mime_type=mime_type,
            request_id=request_id,
            is_fake=False,
            usage=usage,
        )

    @staticmethod
    def _final_output_image(body: dict[str, Any]) -> dict[str, Any] | None:
        steps = body.get("steps")
        if not isinstance(steps, list):
            return None

        final_model_output: dict[str, Any] | None = None
        for step in reversed(steps):
            if isinstance(step, dict) and step.get("type") == "model_output":
                final_model_output = step
                break
        if final_model_output is None:
            return None

        content = final_model_output.get("content")
        if not isinstance(content, list):
            return None
        for block in reversed(content):
            if isinstance(block, dict) and block.get("type") == "image":
                return block
        return None

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }
        if self._client is not None:
            return await self._client.post(
                self.ENDPOINT,
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.post(self.ENDPOINT, headers=headers, json=payload)

    def _build_payload(self, request: GenerationRequest) -> dict[str, Any]:
        inputs: list[dict[str, str]] = [
            {"type": "text", "text": request.prompt},
        ]
        for image in request.images:
            inputs.extend(
                (
                    {"type": "text", "text": f"Reference role: {image.role}"},
                    {
                        "type": "image",
                        "data": base64.b64encode(image.data).decode("ascii"),
                        "mime_type": image.mime_type,
                    },
                )
            )
        return {
            "model": self.MODEL,
            "input": inputs,
            "response_format": {
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": "3:4",
                "image_size": "1K",
            },
        }


class NanoBananaProvider(GeminiProvider):
    """Gemini-native adapter for the approved Nano Banana endpoint."""

    BASE_URL = "https://bananapro.aigenmedia.art"
    DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
    ALLOWED_MODELS = frozenset(
        {
            DEFAULT_MODEL,
            "gemini-3-pro-image-preview",
        }
    )
    VARIANT = "standard"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = DEFAULT_MODEL,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 65.0,
        slow_call_seconds: float = 15.0,
        clock: Any = time.monotonic,
    ) -> None:
        resolved_key = api_key or os.getenv("BANANAPRO_API_KEY")
        if not resolved_key or not resolved_key.strip():
            raise ProviderConfigurationError("Nano Banana API key is required")
        if model_id not in self.ALLOWED_MODELS:
            raise ProviderConfigurationError("Nano Banana model is not approved")
        self._api_key = resolved_key
        self.model_id = model_id
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._slow_call_seconds = slow_call_seconds
        self._clock = clock

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        started = self._clock()
        try:
            response = await self._post(self._build_payload(request))
        except httpx.TimeoutException as error:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from error
        except httpx.HTTPError as error:
            raise ProviderError(ProviderErrorCode.TECHNICAL_FAILURE) from error

        if not response.is_success:
            raise ProviderError(
                ProviderErrorCode.HTTP_ERROR,
                f"Nano Banana returned HTTP {response.status_code}",
                http_status=response.status_code,
                request_id=(
                    response.headers.get("x-request-id")
                    or response.headers.get("x-goog-request-id")
                ),
            )
        try:
            body = response.json()
        except ValueError as error:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from error

        images = self._response_images(body)
        if not images:
            if self._safety_rejected(body):
                raise ProviderError(ProviderErrorCode.SAFETY_REJECTION)
            raise ProviderError(ProviderErrorCode.NO_IMAGE)
        if len(images) != 1:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)

        image_part = images[0]
        try:
            image_bytes = base64.b64decode(image_part["data"], validate=True)
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
        except (binascii.Error, KeyError, TypeError, ValueError, OSError) as error:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from error

        elapsed_seconds = max(0.0, self._clock() - started)
        usage = body.get("usageMetadata") or {}
        if not isinstance(usage, dict):
            usage = {}
        request_id = str(
            body.get("responseId")
            or response.headers.get("x-request-id")
            or response.headers.get("x-goog-request-id")
            or "unknown"
        )
        return ProviderResult(
            provider_mode="nano_banana",
            model=self.model_id,
            variant=self.VARIANT,
            image_bytes=image_bytes,
            mime_type=str(image_part.get("mimeType") or "image/png"),
            request_id=request_id,
            is_fake=False,
            usage=usage,
            elapsed_ms=round(elapsed_seconds * 1000),
            slow_call=elapsed_seconds >= self._slow_call_seconds,
            http_status=response.status_code,
        )

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        url = (
            f"{self.BASE_URL}/api/gemini/v1beta/models/"
            f"{self.model_id}:generateContent"
        )
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }
        if self._client is not None:
            return await self._client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.post(url, headers=headers, json=payload)

    @staticmethod
    def _build_payload(request: GenerationRequest) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": request.prompt}]
        for image in request.images:
            parts.extend(
                (
                    {"text": f"Reference role: {image.role}"},
                    {
                        "inlineData": {
                            "data": base64.b64encode(image.data).decode("ascii"),
                            "mimeType": image.mime_type,
                        }
                    },
                )
            )
        return {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": "3:4", "imageSize": "1K"},
            },
        }

    @staticmethod
    def _response_images(body: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = body.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return []
        first = candidates[0]
        if not isinstance(first, dict):
            return []
        content = first.get("content")
        if not isinstance(content, dict):
            return []
        parts = content.get("parts")
        if not isinstance(parts, list):
            return []
        images: list[dict[str, Any]] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict) and inline_data.get("data"):
                images.append(inline_data)
        return images

    @staticmethod
    def _safety_rejected(body: dict[str, Any]) -> bool:
        candidates = body.get("candidates")
        if not isinstance(candidates, list):
            return False
        return any(
            isinstance(candidate, dict)
            and str(candidate.get("finishReason", "")).upper() == "SAFETY"
            for candidate in candidates
        )


# Preserve the previously published narrow provider name while routing it to the
# only currently approved real provider.
GeminiProvider = NanoBananaProvider
