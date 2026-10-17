from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from comfy_discord.config import Binding, WorkflowProfile
from comfy_discord.workflow import WorkflowError, WorkflowRenderer, load_api_workflow


class WorkflowTests(unittest.TestCase):
    def _profile(self, path: Path) -> WorkflowProfile:
        return WorkflowProfile(
            name="test",
            description="test",
            file=path,
            bindings={
                "prompt": Binding("1", "text"),
                "seed": Binding("2", "seed"),
                "width": Binding("3", "width"),
                "height": Binding("3", "height"),
                "batch_size": Binding("3", "batch_size"),
                "lora_name": Binding("4", "lora_name"),
                "lora_strength": Binding("4", "strength_model"),
            },
        )

    def test_renderer_replaces_bound_values_without_mutating_template(self) -> None:
        graph = {
            "1": {"class_type": "Text", "inputs": {"text": "old"}},
            "2": {"class_type": "Sampler", "inputs": {"seed": 1}},
            "3": {
                "class_type": "Latent",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
            "4": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "default.safetensors", "strength_model": 0.8},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            renderer = WorkflowRenderer(self._profile(path))
            result = renderer.render(
                prompt="new",
                negative_prompt=None,
                width=1024,
                height=768,
                batch_size=2,
                seed=42,
                lora_name="chosen.safetensors",
                lora_strength=1.25,
                filename_prefix="x",
            )
            self.assertEqual(result.seed, 42)
            self.assertEqual(result.graph["1"]["inputs"]["text"], "new")
            self.assertEqual(result.graph["3"]["inputs"]["height"], 768)
            self.assertEqual(result.graph["4"]["inputs"]["lora_name"], "chosen.safetensors")
            self.assertEqual(result.graph["4"]["inputs"]["strength_model"], 1.25)
            self.assertEqual(renderer._template["1"]["inputs"]["text"], "old")

    def test_ui_workflow_is_rejected_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui.json"
            path.write_text('{"nodes": []}', encoding="utf-8")
            with self.assertRaisesRegex(WorkflowError, r"Export \(API\)"):
                load_api_workflow(path)

    def test_comfy_resolution_selector_dimensions_are_accepted(self) -> None:
        graph = {
            "1": {"class_type": "Text", "inputs": {"text": "old"}},
            "2": {"class_type": "Sampler", "inputs": {"seed": 1}},
            "3": {
                "class_type": "Latent",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
            "4": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "default.safetensors", "strength_model": 0.8},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            renderer = WorkflowRenderer(self._profile(path))
            result = renderer.render(
                prompt="x",
                negative_prompt=None,
                width=888,
                height=1184,
                batch_size=1,
                seed=1,
                lora_name=None,
                lora_strength=None,
                filename_prefix="x",
            )
            self.assertEqual(result.graph["3"]["inputs"]["width"], 888)
            self.assertEqual(result.graph["3"]["inputs"]["height"], 1184)

    def test_dimensions_must_be_divisible_by_8(self) -> None:
        graph = {
            "1": {"class_type": "Text", "inputs": {"text": "old"}},
            "2": {"class_type": "Sampler", "inputs": {"seed": 1}},
            "3": {
                "class_type": "Latent",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
            "4": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "default.safetensors", "strength_model": 0.8},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            renderer = WorkflowRenderer(self._profile(path))
            with self.assertRaisesRegex(WorkflowError, "durch 8"):
                renderer.render(
                    prompt="x",
                    negative_prompt=None,
                    width=1001,
                    height=1024,
                    batch_size=1,
                    seed=1,
                    lora_name=None,
                    lora_strength=None,
                    filename_prefix="x",
                )


if __name__ == "__main__":
    unittest.main()

