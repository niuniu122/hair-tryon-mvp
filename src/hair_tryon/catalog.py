from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Hairstyle:
    hairstyle_id: str
    name: str


HAIRSTYLES = (
    Hairstyle("H01", "Buzz Cut"),
    Hairstyle("H02", "Crew Cut"),
    Hairstyle("H03", "French Crop"),
    Hairstyle("H04", "Side Part"),
    Hairstyle("H05", "Short Quiff"),
)


def get_hairstyle(hairstyle_id: str) -> Hairstyle | None:
    return next(
        (style for style in HAIRSTYLES if style.hairstyle_id == hairstyle_id),
        None,
    )
