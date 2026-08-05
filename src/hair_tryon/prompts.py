from __future__ import annotations

from hair_tryon.catalog import Hairstyle
from hair_tryon.domain import ViewName


PROMPT_VERSION = "hair-tryon-mvp-v1"


def build_prompt(hairstyle: Hairstyle, view: ViewName) -> str:
    if view is ViewName.BACK:
        return (
            f"Create an AI-inferred back view for hairstyle {hairstyle.hairstyle_id} "
            f"({hairstyle.name}). Preserve the same subject and hairstyle structure."
        )
    return (
        f"Apply hairstyle {hairstyle.hairstyle_id} ({hairstyle.name}) to the "
        f"provided subject while preserving identity and the {view.value} view."
    )
