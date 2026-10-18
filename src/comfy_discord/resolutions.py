from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolutionPreset:
    value: str
    label: str
    width: int
    height: int

    @property
    def discord_name(self) -> str:
        return f"{self.value} {self.label} ({self.width}x{self.height})"


# These are the 1 MP results produced by ComfyUI's ResolutionSelector with
# `multiple=8`. Keeping the same values makes the Discord and ComfyUI choices
# interchangeable.
RESOLUTION_PRESETS = (
    ResolutionPreset("1:1", "Quadrat", 1024, 1024),
    ResolutionPreset("2:3", "Portraet-Foto", 840, 1256),
    ResolutionPreset("3:2", "Foto", 1256, 840),
    ResolutionPreset("3:4", "Portraet Standard", 888, 1184),
    ResolutionPreset("4:3", "Standard", 1184, 888),
    ResolutionPreset("9:16", "Portraet Breitbild", 768, 1368),
    ResolutionPreset("16:9", "Breitbild", 1368, 768),
    ResolutionPreset("21:9", "Ultrawide", 1536, 672),
)

RESOLUTION_PRESETS_BY_VALUE = {preset.value: preset for preset in RESOLUTION_PRESETS}


IMAGE_RESOLUTION_CHOICES = (
    "512x512",
    "768x768",
    "1024x1024",
    "1280x1280",
    "1536x1536",
    "768x1024",
    "1024x768",
    "888x1184",
    "1184x888",
    "768x1368",
    "1368x768",
)


def parse_image_resolution(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d{3,4})\s*[xX×]\s*(\d{3,4})\s*", value)
    if match is None:
        raise ValueError("Aufloesung muss im Format BREITExHOEHE stehen, z. B. 1024x1024.")

    width, height = (int(part) for part in match.groups())
    if not 256 <= width <= 2048 or not 256 <= height <= 2048:
        raise ValueError("Breite und Hoehe muessen jeweils zwischen 256 und 2048 liegen.")
    return width, height


# MiniMax H3 uses a native 768 px short edge, a 768x1344 area cap, and
# dimensions divisible by 32. These presets stay within that native canvas.
VIDEO_RESOLUTION_PRESETS = (
    ResolutionPreset("1:1", "Quadrat", 768, 768),
    ResolutionPreset("2:3", "Portraet-Foto", 768, 1152),
    ResolutionPreset("3:2", "Foto", 1152, 768),
    ResolutionPreset("3:4", "Portraet Standard", 768, 1024),
    ResolutionPreset("4:3", "Standard", 1024, 768),
    ResolutionPreset("9:16", "Portraet Breitbild", 768, 1344),
    ResolutionPreset("16:9", "Breitbild", 1344, 768),
    ResolutionPreset("21:9", "Ultrawide", 1568, 672),
)

VIDEO_RESOLUTION_PRESETS_BY_VALUE = {
    preset.value: preset for preset in VIDEO_RESOLUTION_PRESETS
}
