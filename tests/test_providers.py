import base64
import io

import httpx
import pytest
from PIL import Image

from hair_tryon.domain import ViewName
from hair_tryon.providers import (
    FakeProvider,
    FakeScenario,
    GenerationRequest,
    NanoBananaProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderErrorCode,
    ProviderImage,
)


def generation_request(*, attempt: int = 1) -> GenerationRequest:
    return GenerationRequest(
        generation_set_id="set-1",
        view=ViewName.FRONT,
        attempt=attempt,
        prompt="Change only the hairstyle.",
        prompt_version="front-v1",
        images=(
            ProviderImage(
                role="source_front",
                mime_type="image/png",
                data=b"source-image",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_fake_provider_is_deterministic_and_explicitly_fake() -> None:
    provider = FakeProvider()
    request = generation_request()

    first = await provider.generate(request)
    second = await provider.generate(request)

    assert first.provider_mode == "fake"
    assert first.is_fake is True
    assert first.model == "fake-deterministic"
    assert first.image_bytes == second.image_bytes
    assert first.request_id == second.request_id

    image = Image.open(io.BytesIO(first.image_bytes))
    assert image.format == "PNG"
    assert image.info["Comment"] == "FAKE - NOT MODEL OUTPUT"


@pytest.mark.asyncio
async def test_fake_fail_first_succeeds_only_on_second_attempt() -> None:
    provider = FakeProvider(FakeScenario.FAIL_FIRST)

    with pytest.raises(ProviderError) as first_error:
        await provider.generate(generation_request(attempt=1))
    assert first_error.value.code is ProviderErrorCode.TECHNICAL_FAILURE

    result = await provider.generate(generation_request(attempt=2))
    assert result.is_fake is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        (FakeScenario.ALWAYS_FAIL, ProviderErrorCode.TECHNICAL_FAILURE),
        (FakeScenario.TIMEOUT, ProviderErrorCode.TIMEOUT),
        (FakeScenario.SAFETY_REJECTION, ProviderErrorCode.SAFETY_REJECTION),
    ],
)
async def test_fake_provider_exposes_deterministic_failure_scenarios(
    scenario: FakeScenario,
    expected_code: ProviderErrorCode,
) -> None:
    provider = FakeProvider(scenario)

    with pytest.raises(ProviderError) as error:
        await provider.generate(generation_request())

    assert error.value.code is expected_code


def test_nano_banana_provider_requires_its_server_side_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BANANAPRO_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-key-must-not-be-used")
    monkeypatch.setenv("GOOGLE_API_KEY", "legacy-key-must-not-be-used")

    with pytest.raises(ProviderConfigurationError):
        NanoBananaProvider()


@pytest.mark.asyncio
async def test_nano_banana_uses_approved_endpoint_and_native_image_contract() -> None:
    captured: dict[str, object] = {}
    generated_output = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(generated_output, format="PNG")
    generated = generated_output.getvalue()
    clock_values = iter((0.0, 16.0))

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-goog-api-key")
        captured["payload"] = __import__("json").loads(request.content)
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(
            200,
            json={
                "responseId": "response-1",
                "modelVersion": "gemini-3.1-flash-image-preview",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Final rendered image."},
                                {
                                    "inlineData": {
                                        "data": base64.b64encode(generated).decode(
                                            "ascii"
                                        ),
                                        "mimeType": "image/png",
                                    }
                                },
                            ]
                        }
                    }
                ],
                "usageMetadata": {"totalTokenCount": 17},
            },
            headers={"x-request-id": "header-request-id"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = NanoBananaProvider(
            api_key="test-secret",
            client=client,
            clock=lambda: next(clock_values),
        )
        result = await provider.generate(generation_request())

    assert captured["url"] == (
        "https://bananapro.aigenmedia.art/api/gemini/v1beta/models/"
        "gemini-3.1-flash-image-preview:generateContent"
    )
    assert captured["key"] == "test-secret"
    assert captured["payload"] == {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Change only the hairstyle."},
                    {"text": "Reference role: source_front"},
                    {
                        "inlineData": {
                            "data": base64.b64encode(b"source-image").decode("ascii"),
                            "mimeType": "image/png",
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "3:4", "imageSize": "1K"},
        },
    }
    assert captured["timeout"] == {
        "connect": 65.0,
        "read": 65.0,
        "write": 65.0,
        "pool": 65.0,
    }
    assert result.provider_mode == "nano_banana"
    assert result.is_fake is False
    assert result.model == "gemini-3.1-flash-image-preview"
    assert result.variant == "standard"
    assert result.image_bytes == generated
    assert result.mime_type == "image/png"
    assert result.request_id == "response-1"
    assert result.usage == {"totalTokenCount": 17}
    assert result.elapsed_ms == 16_000
    assert result.slow_call is True


@pytest.mark.asyncio
async def test_nano_banana_rejects_success_response_without_an_image() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"responseId": "no-image"})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        provider = NanoBananaProvider(api_key="test-secret", client=client)

        with pytest.raises(ProviderError) as error:
            await provider.generate(generation_request())

    assert error.value.code is ProviderErrorCode.NO_IMAGE


def test_nano_banana_rejects_unapproved_model_ids() -> None:
    with pytest.raises(ProviderConfigurationError):
        NanoBananaProvider(api_key="test-secret", model_id="nano-banana-plus")


@pytest.mark.asyncio
async def test_nano_banana_maps_hard_timeout_without_leaking_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret test-secret must not escape", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = NanoBananaProvider(api_key="test-secret", client=client)

        with pytest.raises(ProviderError) as error:
            await provider.generate(generation_request())

    assert error.value.code is ProviderErrorCode.TIMEOUT
    assert "test-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_nano_banana_preserves_non_success_http_metadata_without_body() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            429,
            text="upstream body must not enter telemetry",
            headers={"x-request-id": "request-429"},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        provider = NanoBananaProvider(api_key="test-secret", client=client)

        with pytest.raises(ProviderError) as error:
            await provider.generate(generation_request())

    assert error.value.code is ProviderErrorCode.HTTP_ERROR
    assert error.value.http_status == 429
    assert error.value.request_id == "request-429"
    assert "upstream body" not in str(error.value)
