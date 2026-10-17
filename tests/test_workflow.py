from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from comfy_discord.config import Binding, WorkflowProfile
from comfy_discord.workflow import (
    VideoWorkflowRenderer,
    WorkflowError,
    WorkflowRenderer,
    load_api_workflow,
)


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
                steps=None,
                cfg_scale=None,
                filename_prefix="x",
            )
            self.assertEqual(result.seed, 42)
            self.assertEqual(result.graph["1"]["inputs"]["text"], "new")
            self.assertEqual(result.graph["3"]["inputs"]["height"], 768)
            self.assertEqual(result.graph["4"]["inputs"]["lora_name"], "chosen.safetensors")
            self.assertEqual(result.graph["4"]["inputs"]["strength_model"], 1.25)
            self.assertEqual(renderer._template["1"]["inputs"]["text"], "old")

    def test_renderer_applies_steps_and_cfg_when_requested(self) -> None:
        graph = {
            "1": {"class_type": "Text", "inputs": {"text": "old"}},
            "2": {
                "class_type": "Sampler",
                "inputs": {"seed": 1, "steps": 25, "cfg": 2.5},
            },
            "3": {
                "class_type": "Latent",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            profile = WorkflowProfile(
                name="sampling-test",
                description="test",
                file=path,
                bindings={
                    "prompt": Binding("1", "text"),
                    "seed": Binding("2", "seed"),
                    "steps": Binding("2", "steps"),
                    "cfg_scale": Binding("2", "cfg"),
                    "width": Binding("3", "width"),
                    "height": Binding("3", "height"),
                    "batch_size": Binding("3", "batch_size"),
                },
            )
            renderer = WorkflowRenderer(profile)
            result = renderer.render(
                prompt="x",
                negative_prompt=None,
                width=1024,
                height=1024,
                batch_size=1,
                seed=1,
                lora_name=None,
                lora_strength=None,
                steps=40,
                cfg_scale=4.5,
                filename_prefix="x",
            )
            self.assertEqual(result.graph["2"]["inputs"]["steps"], 40)
            self.assertEqual(result.graph["2"]["inputs"]["cfg"], 4.5)
            self.assertEqual(renderer._template["2"]["inputs"]["steps"], 25)
            self.assertEqual(renderer._template["2"]["inputs"]["cfg"], 2.5)

    def test_ui_workflow_is_rejected_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui.json"
            path.write_text('{"nodes": []}', encoding="utf-8")
            with self.assertRaisesRegex(WorkflowError, r"Export \(API\)"):
                load_api_workflow(path)

    def test_renderer_applies_three_lora_slots(self) -> None:
        graph = {
            "1": {"class_type": "Text", "inputs": {"text": "old"}},
            "2": {"class_type": "Sampler", "inputs": {"seed": 1}},
            "3": {
                "class_type": "Latent",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
            "4": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "one.safetensors", "strength_model": 1.0},
            },
            "5": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "two.safetensors", "strength_model": 0.0},
            },
            "6": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "three.safetensors", "strength_model": 0.0},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            base_profile = self._profile(path)
            profile = WorkflowProfile(
                name=base_profile.name,
                description=base_profile.description,
                file=base_profile.file,
                bindings={
                    **base_profile.bindings,
                    "lora_2_name": Binding("5", "lora_name"),
                    "lora_2_strength": Binding("5", "strength_model"),
                    "lora_3_name": Binding("6", "lora_name"),
                    "lora_3_strength": Binding("6", "strength_model"),
                },
            )
            renderer = WorkflowRenderer(profile)
            result = renderer.render(
                prompt="x",
                negative_prompt=None,
                width=1024,
                height=1024,
                batch_size=1,
                seed=1,
                lora_name="first.safetensors",
                lora_strength=0.8,
                lora_2_name="second.safetensors",
                lora_2_strength=0.6,
                lora_3_name="third.safetensors",
                lora_3_strength=1.2,
                filename_prefix="x",
            )
            self.assertEqual(result.graph["4"]["inputs"]["strength_model"], 0.8)
            self.assertEqual(result.graph["5"]["inputs"]["lora_name"], "second.safetensors")
            self.assertEqual(result.graph["5"]["inputs"]["strength_model"], 0.6)
            self.assertEqual(result.graph["6"]["inputs"]["lora_name"], "third.safetensors")
            self.assertEqual(result.graph["6"]["inputs"]["strength_model"], 1.2)

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

    def test_profile_specific_dimension_grid_and_normalization(self) -> None:
        graph = {
            "1": {"class_type": "Text", "inputs": {"text": "old"}},
            "2": {"class_type": "Sampler", "inputs": {"seed": 1}},
            "3": {
                "class_type": "Latent",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            profile = WorkflowProfile(
                name="moss",
                description="moss",
                file=path,
                bindings={
                    "prompt": Binding("1", "text"),
                    "seed": Binding("2", "seed"),
                    "width": Binding("3", "width"),
                    "height": Binding("3", "height"),
                    "batch_size": Binding("3", "batch_size"),
                },
                dimension_multiple=16,
            )
            renderer = WorkflowRenderer(profile)
            self.assertEqual(renderer.normalize_dimensions(888, 1184), (896, 1184))
            with self.assertRaisesRegex(WorkflowError, "durch 16"):
                renderer.render(
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

    def test_moss_workflow_has_expected_native_model_stack(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / "workflows"
            / "moss_image_sft_api.json"
        )
        graph = load_api_workflow(workflow_path)
        self.assertEqual(
            graph["1"]["inputs"]["unet_name"],
            "moss_image_sft_int8_convrot.safetensors",
        )
        self.assertEqual(graph["2"]["inputs"]["type"], "moss_image")
        self.assertEqual(graph["8"]["inputs"]["steps"], 25)
        self.assertEqual(graph["8"]["inputs"]["sampler_name"], "er_sde")

    def test_video_renderer_binds_prompt_dimensions_duration_and_seed(self) -> None:
        graph = {
            "1": {
                "class_type": "MiniMaxH3ImageToVideo",
                "inputs": {"prompt": "old", "width": 1344, "height": 768, "length": 124},
            },
            "2": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1}},
            "3": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "old"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            profile = WorkflowProfile(
                name="video",
                description="video",
                file=path,
                bindings={
                    "prompt": Binding("1", "prompt"),
                    "width": Binding("1", "width"),
                    "height": Binding("1", "height"),
                    "length": Binding("1", "length"),
                    "seed": Binding("2", "noise_seed"),
                    "filename_prefix": Binding("3", "filename_prefix"),
                },
            )
            renderer = VideoWorkflowRenderer(profile)
            result = renderer.render_video(
                prompt="a moving scene",
                width=768,
                height=1344,
                duration_seconds=5,
                seed=42,
                filename_prefix="Discord/video",
            )
            self.assertEqual(result.seed, 42)
            self.assertEqual(result.frame_count, 124)
            self.assertEqual(result.graph["1"]["inputs"]["prompt"], "a moving scene")
            self.assertEqual(result.graph["1"]["inputs"]["width"], 768)
            self.assertEqual(result.graph["1"]["inputs"]["height"], 1344)
            self.assertEqual(result.graph["1"]["inputs"]["length"], 124)
            self.assertEqual(result.graph["2"]["inputs"]["noise_seed"], 42)
            self.assertEqual(result.graph["3"]["inputs"]["filename_prefix"], "Discord/video")

    def test_video_duration_is_aligned_to_minimax_frame_grid(self) -> None:
        self.assertEqual(VideoWorkflowRenderer.duration_to_frames(5), 124)
        self.assertEqual(VideoWorkflowRenderer.duration_to_frames(10), 243)
        self.assertEqual(VideoWorkflowRenderer.duration_to_frames(15), 362)

    def test_minimax_save_video_uses_flat_dynamic_combo_inputs(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / "workflows"
            / "minimax_h3_t2v_api.json"
        )
        graph = load_api_workflow(workflow_path)
        save_inputs = graph["92"]["inputs"]
        self.assertEqual(save_inputs["format"], "mp4")
        self.assertEqual(save_inputs["format.codec"], "h264")
        self.assertEqual(save_inputs["format.codec.encoding"], "re-encode")
        self.assertEqual(save_inputs["format.codec.encoding.crf"], 23)


if __name__ == "__main__":
    unittest.main()

