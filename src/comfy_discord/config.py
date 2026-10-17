from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when local bot configuration is incomplete or invalid."""


@dataclass(frozen=True)
class Binding:
    node: str
    input: str


@dataclass(frozen=True)
class WorkflowProfile:
    name: str
    description: str
    file: Path
    bindings: dict[str, Binding]


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    discord_token: str | None
    discord_guild_id: int | None
    comfy_url: str
    allowed_channel_ids: frozenset[int]
    max_parallel_jobs: int
    generation_timeout_seconds: int
    log_level: str
    default_workflow: str
    max_prompt_length: int
    max_files_per_message: int
    workflows: dict[str, WorkflowProfile]


def _load_dotenv(path: Path) -> None:
    """Load the small subset of dotenv syntax needed by this project."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _optional_int(value: str | None, label: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{label} muss eine ganze Zahl sein.") from exc


def _positive_int(value: str, label: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise ConfigError(f"{label} muss eine ganze Zahl sein.") from exc
    if result < 1:
        raise ConfigError(f"{label} muss mindestens 1 sein.")
    return result


def _id_set(value: str | None, label: str) -> frozenset[int]:
    if not value or not value.strip():
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ConfigError(f"{label} enthaelt eine ungueltige Discord-ID.") from exc


def load_settings(
    project_dir: Path | None = None,
    *,
    require_token: bool = True,
) -> Settings:
    root = (project_dir or Path(os.environ.get("BOT_HOME", Path.cwd()))).resolve()
    _load_dotenv(root / ".env")

    config_path = Path(os.environ.get("BOT_CONFIG", root / "config.json"))
    if not config_path.is_absolute():
        config_path = root / config_path
    if not config_path.is_file():
        raise ConfigError(f"Konfigurationsdatei fehlt: {config_path}")

    try:
        raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Konfiguration kann nicht gelesen werden: {exc}") from exc

    profiles: dict[str, WorkflowProfile] = {}
    for name, entry in raw.get("workflows", {}).items():
        if not isinstance(entry, dict):
            raise ConfigError(f"Workflow {name!r} muss ein Objekt sein.")
        workflow_file = Path(str(entry.get("file", "")))
        if not workflow_file.is_absolute():
            workflow_file = config_path.parent / workflow_file
        bindings: dict[str, Binding] = {}
        for parameter, binding in entry.get("bindings", {}).items():
            if not isinstance(binding, dict) or "node" not in binding or "input" not in binding:
                raise ConfigError(f"Ungueltiges Binding {parameter!r} in Workflow {name!r}.")
            bindings[parameter] = Binding(str(binding["node"]), str(binding["input"]))
        profiles[name] = WorkflowProfile(
            name=name,
            description=str(entry.get("description", name)),
            file=workflow_file.resolve(),
            bindings=bindings,
        )

    if not profiles:
        raise ConfigError("Mindestens ein Workflow muss in config.json konfiguriert sein.")
    default_workflow = str(raw.get("default_workflow", ""))
    if default_workflow not in profiles:
        raise ConfigError("default_workflow verweist nicht auf einen konfigurierten Workflow.")

    token = os.environ.get("DISCORD_TOKEN", "").strip() or None
    if require_token and not token:
        raise ConfigError("DISCORD_TOKEN fehlt in .env.")

    comfy_url = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").strip().rstrip("/")
    if not comfy_url.startswith(("http://", "https://")):
        raise ConfigError("COMFYUI_URL muss mit http:// oder https:// beginnen.")

    return Settings(
        project_dir=root,
        discord_token=token,
        discord_guild_id=_optional_int(os.environ.get("DISCORD_GUILD_ID"), "DISCORD_GUILD_ID"),
        comfy_url=comfy_url,
        allowed_channel_ids=_id_set(os.environ.get("ALLOWED_CHANNEL_IDS"), "ALLOWED_CHANNEL_IDS"),
        max_parallel_jobs=_positive_int(os.environ.get("MAX_PARALLEL_JOBS", "1"), "MAX_PARALLEL_JOBS"),
        generation_timeout_seconds=_positive_int(
            os.environ.get("GENERATION_TIMEOUT_SECONDS", "1200"),
            "GENERATION_TIMEOUT_SECONDS",
        ),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        default_workflow=default_workflow,
        max_prompt_length=int(raw.get("max_prompt_length", 4000)),
        max_files_per_message=min(10, max(1, int(raw.get("max_files_per_message", 10)))),
        workflows=profiles,
    )

