from __future__ import annotations

import copy
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import WorkflowProfile


class WorkflowError(ValueError):
    """Raised when a workflow is not an API workflow or cannot be bound."""


@dataclass(frozen=True)
class RenderedWorkflow:
    graph: dict[str, Any]
    seed: int


@dataclass(frozen=True)
class RenderedVideoWorkflow:
    graph: dict[str, Any]
    seed: int
    frame_count: int


def load_api_workflow(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WorkflowError(f"Workflow-Datei fehlt: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Workflow kann nicht gelesen werden: {exc}") from exc

    if isinstance(raw, dict) and isinstance(raw.get("prompt"), dict):
        raw = raw["prompt"]
    if isinstance(raw, dict) and isinstance(raw.get("nodes"), list):
        raise WorkflowError(
            f"{path.name} ist ein UI-Workflow. Bitte in ComfyUI ueber "
            "'File -> Export (API)' exportieren."
        )
    if not isinstance(raw, dict) or not raw:
        raise WorkflowError(f"{path.name} enthaelt keinen API-Workflow.")
    for node_id, node in raw.items():
        if not isinstance(node, dict) or "class_type" not in node or not isinstance(node.get("inputs"), dict):
            raise WorkflowError(f"Node {node_id!r} in {path.name} hat kein gueltiges API-Format.")
    return raw


class WorkflowRenderer:
    def __init__(self, profile: WorkflowProfile):
        self.profile = profile
        self._template = load_api_workflow(profile.file)
        self._validate_bindings()

    def _validate_bindings(self) -> None:
        for parameter, binding in self.profile.bindings.items():
            node = self._template.get(binding.node)
            if node is None:
                raise WorkflowError(
                    f"Binding {parameter!r}: Node {binding.node!r} fehlt in {self.profile.file.name}."
                )
            if binding.input not in node["inputs"]:
                raise WorkflowError(
                    f"Binding {parameter!r}: Input {binding.input!r} fehlt an Node {binding.node!r}."
                )

    def _bind_values(self, values: dict[str, Any]) -> dict[str, Any]:
        graph = copy.deepcopy(self._template)
        for parameter, value in values.items():
            binding = self.profile.bindings.get(parameter)
            if binding is not None:
                graph[binding.node]["inputs"][binding.input] = value
        return graph

    def render(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        width: int,
        height: int,
        batch_size: int,
        seed: int,
        lora_name: str | None,
        lora_strength: float | None,
        filename_prefix: str,
        lora_2_name: str | None = None,
        lora_2_strength: float | None = None,
        lora_3_name: str | None = None,
        lora_3_strength: float | None = None,
    ) -> RenderedWorkflow:
        if not prompt.strip():
            raise WorkflowError("Der Prompt darf nicht leer sein.")
        if width % 8 or height % 8:
            raise WorkflowError("Breite und Hoehe muessen durch 8 teilbar sein.")
        if not 1 <= batch_size <= 4:
            raise WorkflowError("Es sind 1 bis 4 Bilder pro Auftrag erlaubt.")

        actual_seed = secrets.randbelow(2**53) if seed < 0 else seed
        values: dict[str, Any] = {
            "prompt": prompt.strip(),
            "width": width,
            "height": height,
            "batch_size": batch_size,
            "seed": actual_seed,
            "filename_prefix": filename_prefix,
        }
        if negative_prompt is not None:
            values["negative_prompt"] = negative_prompt.strip()
        if lora_name is not None:
            values["lora_name"] = lora_name
        if lora_strength is not None:
            values["lora_strength"] = lora_strength
        if lora_2_name is not None:
            values["lora_2_name"] = lora_2_name
        if lora_2_strength is not None:
            values["lora_2_strength"] = lora_2_strength
        if lora_3_name is not None:
            values["lora_3_name"] = lora_3_name
        if lora_3_strength is not None:
            values["lora_3_strength"] = lora_3_strength

        graph = self._bind_values(values)
        return RenderedWorkflow(graph=graph, seed=actual_seed)


class VideoWorkflowRenderer(WorkflowRenderer):
    @staticmethod
    def duration_to_frames(duration_seconds: int) -> int:
        frame_count = max(5, round(duration_seconds * 24))
        return frame_count + (5 - frame_count % 17) % 17

    def render_video(
        self,
        *,
        prompt: str,
        width: int,
        height: int,
        duration_seconds: int,
        seed: int,
        filename_prefix: str,
    ) -> RenderedVideoWorkflow:
        if not prompt.strip():
            raise WorkflowError("Der Prompt darf nicht leer sein.")
        if width % 32 or height % 32:
            raise WorkflowError("Video-Breite und -Hoehe muessen durch 32 teilbar sein.")
        if not 5 <= duration_seconds <= 15:
            raise WorkflowError("Die Videodauer muss zwischen 5 und 15 Sekunden liegen.")

        actual_seed = secrets.randbelow(2**53) if seed < 0 else seed
        frame_count = self.duration_to_frames(duration_seconds)
        graph = self._bind_values(
            {
                "prompt": prompt.strip(),
                "width": width,
                "height": height,
                "length": frame_count,
                "seed": actual_seed,
                "filename_prefix": filename_prefix,
            }
        )
        return RenderedVideoWorkflow(
            graph=graph,
            seed=actual_seed,
            frame_count=frame_count,
        )


def validate_profiles(profiles: dict[str, WorkflowProfile]) -> None:
    for profile in profiles.values():
        WorkflowRenderer(profile)


def validate_video_profiles(profiles: dict[str, WorkflowProfile]) -> None:
    for profile in profiles.values():
        VideoWorkflowRenderer(profile)

