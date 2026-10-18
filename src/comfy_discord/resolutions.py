from __future__ import annotations

import math
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

    @property
    def image_discord_name(self) -> str:
        return f"{self.value} {self.label}"


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


def dimensions_for_megapixels(
    width: int,
    height: int,
    megapixels: float,
) -> tuple[int, int]:
    """Scale an aspect-ratio canvas to the requested diffusion megapixel area."""
    if width < 1 or height < 1:
        raise ValueError("Breite und Hoehe muessen positiv sein.")
    if megapixels <= 0:
        raise ValueError("Megapixel muss groesser als 0 sein.")

    # Image-generation tools conventionally treat 1024x1024 as a 1 MP canvas.
    target_pixels = megapixels * 1024 * 1024
    scale = math.sqrt(target_pixels / (width * height))
    return max(1, round(width * scale)), max(1, round(height * scale))


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
