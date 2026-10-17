from __future__ import annotations

import argparse
import logging
import sys

from comfy_discord.config import ConfigError, load_settings
from comfy_discord.workflow import WorkflowError, validate_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Discord-Bot fuer eine lokale ComfyUI-Instanz")
    parser.add_argument("--check", action="store_true", help="Konfiguration pruefen und beenden")
    args = parser.parse_args()

    try:
        settings = load_settings(require_token=not args.check)
        validate_profiles(settings.workflows)
    except (ConfigError, WorkflowError) as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.check:
        token_status = "gesetzt" if settings.discord_token else "fehlt noch"
        print("Konfiguration ist gueltig.")
        print(f"ComfyUI: {settings.comfy_url}")
        print(f"Discord-Token: {token_status}")
        print(f"Workflows: {', '.join(settings.workflows)}")
        return

    from comfy_discord.bot import run_bot

    run_bot(settings)


if __name__ == "__main__":
    main()

