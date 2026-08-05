from __future__ import annotations

import os
from dataclasses import dataclass

from hair_tryon.providers import ProviderConfigurationError


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    provider_mode: str

    @classmethod
    def from_environment(cls) -> RuntimeConfig:
        provider_mode = os.getenv("HAIR_TRYON_PROVIDER", "fake").strip().casefold()
        if provider_mode not in {"fake", "nano_banana"}:
            raise ProviderConfigurationError("HAIR_TRYON_PROVIDER is invalid")
        return cls(provider_mode=provider_mode)
