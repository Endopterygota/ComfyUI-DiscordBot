from __future__ import annotations

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
    ResolutionPreset("21:9", "Ultrawide", 1568, 672),
)

RESOLUTION_PRESETS_BY_VALUE = {preset.value: preset for preset in RESOLUTION_PRESETS}
