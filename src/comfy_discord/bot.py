from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from datetime import datetime

import discord
from discord import app_commands

from .comfy import ComfyClient, ComfyError
from .config import Settings
from .workflow import WorkflowError, WorkflowRenderer


LOGGER = logging.getLogger(__name__)


class ComfyDiscordBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.none())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.comfy = ComfyClient(settings.comfy_url, settings.generation_timeout_seconds)
        self.renderers = {name: WorkflowRenderer(profile) for name, profile in settings.workflows.items()}
        self.gpu_slots = asyncio.Semaphore(settings.max_parallel_jobs)
        self._queue_lock = asyncio.Lock()
        self._waiting = 0
        self._active = 0
        self._lora_cache: list[str] = []
        self._lora_cache_time = 0.0
        self._lora_aliases: dict[str, str] = {}
        self._register_commands()

    async def setup_hook(self) -> None:
        await self.comfy.start()
        if self.settings.discord_guild_id is not None:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            LOGGER.info("Slash-Commands fuer Discord-Server %s synchronisiert.", guild.id)
        else:
            await self.tree.sync()
            LOGGER.info("Globale Slash-Commands synchronisiert.")

    async def close(self) -> None:
        await self.comfy.close()
        await super().close()

    async def on_ready(self) -> None:
        LOGGER.info("Angemeldet als %s (%s).", self.user, self.user.id if self.user else "?")

    def _channel_allowed(self, interaction: discord.Interaction) -> bool:
        allowed = self.settings.allowed_channel_ids
        return not allowed or interaction.channel_id in allowed

    async def _queue_enter(self) -> int:
        async with self._queue_lock:
            self._waiting += 1
            return self._active + self._waiting

    async def _queue_activate(self) -> None:
        async with self._queue_lock:
            self._waiting -= 1
            self._active += 1

    async def _queue_leave(self) -> None:
        async with self._queue_lock:
            self._active -= 1

    @staticmethod
    def _lora_alias(filename: str) -> str:
        digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:20]
        return f"lora-{digest}"

    async def _list_loras(self, *, force: bool = False) -> list[str]:
        if force or not self._lora_cache or time.monotonic() - self._lora_cache_time > 30:
            filenames = await self.comfy.list_models("loras")
            self._lora_cache = filenames
            self._lora_cache_time = time.monotonic()
            self._lora_aliases = {self._lora_alias(filename): filename for filename in filenames}
        return self._lora_cache

    async def _resolve_lora(self, value: str) -> str | None:
        await self._list_loras()
        if value in self._lora_aliases:
            return self._lora_aliases[value]
        # Also accept an exact filename typed manually.
        return value if value in self._lora_cache else None

    def _register_commands(self) -> None:
        @self.tree.command(name="bild", description="Erzeugt Bilder mit ComfyUI")
        @app_commands.describe(
            prompt="Was soll erzeugt werden?",
            negative="Optionaler negativer Prompt; leer behaelt den Workflow-Standard",
            breite="Bildbreite, durch 64 teilbar",
            hoehe="Bildhoehe, durch 64 teilbar",
            seed="-1 fuer zufaelligen Seed",
            bilder="Anzahl der Bilder (1 bis 4)",
            lora="Installierte LoRA; leer behaelt den Workflow-Standard",
            lora_staerke="LoRA-Staerke; leer behaelt den Workflow-Standard",
            workflow="Workflow-Profil; leer nutzt den Standard",
        )
        async def image_command(
            interaction: discord.Interaction,
            prompt: app_commands.Range[str, 1, 4000],
            negative: app_commands.Range[str, 0, 4000] | None = None,
            breite: app_commands.Range[int, 256, 2048] = 1024,
            hoehe: app_commands.Range[int, 256, 2048] = 1024,
            seed: app_commands.Range[int, -1, 9007199254740991] = -1,
            bilder: app_commands.Range[int, 1, 4] = 1,
            lora: str | None = None,
            lora_staerke: app_commands.Range[float, 0.0, 2.0] | None = None,
            workflow: str | None = None,
        ) -> None:
            if not self._channel_allowed(interaction):
                await interaction.response.send_message("Dieser Kanal ist fuer den Bot nicht freigegeben.", ephemeral=True)
                return
            if len(prompt) > self.settings.max_prompt_length:
                await interaction.response.send_message("Der Prompt ist zu lang.", ephemeral=True)
                return

            profile_name = workflow or self.settings.default_workflow
            renderer = self.renderers.get(profile_name)
            if renderer is None:
                available = ", ".join(self.renderers)
                await interaction.response.send_message(
                    f"Unbekannter Workflow. Verfuegbar: {available}", ephemeral=True
                )
                return

            selected_lora: str | None = None
            selected_strength = lora_staerke
            lora_label = "Workflow-Standard"
            if lora == "__none__":
                selected_strength = 0.0
                lora_label = "keine"
            elif lora == "__default__" or lora is None:
                pass
            else:
                try:
                    selected_lora = await self._resolve_lora(lora)
                except ComfyError as exc:
                    await interaction.response.send_message(str(exc), ephemeral=True)
                    return
                if selected_lora is None:
                    await interaction.response.send_message(
                        "Diese LoRA ist in der laufenden ComfyUI-Installation nicht mehr vorhanden.",
                        ephemeral=True,
                    )
                    return
                if selected_strength is None:
                    selected_strength = 1.0
                lora_label = selected_lora

            try:
                rendered = renderer.render(
                    prompt=prompt,
                    negative_prompt=negative,
                    width=breite,
                    height=hoehe,
                    batch_size=bilder,
                    seed=seed,
                    lora_name=selected_lora,
                    lora_strength=selected_strength,
                    filename_prefix=f"Discord/{interaction.user.id}/krea2",
                )
            except WorkflowError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return

            await interaction.response.defer(thinking=True)
            position = await self._queue_enter()
            await interaction.edit_original_response(
                content=f"Auftrag angenommen (Warteschlangenposition: {position})."
            )

            acquired = False
            try:
                await self.gpu_slots.acquire()
                acquired = True
                await self._queue_activate()
                await interaction.edit_original_response(content="ComfyUI erzeugt das Bild …")
                files = await self.comfy.generate(rendered.graph)
                selected = files[: self.settings.max_files_per_message]
                discord_files = [
                    discord.File(io.BytesIO(item.content), filename=item.filename)
                    for item in selected
                ]
                omitted = len(files) - len(selected)
                suffix = f" ({omitted} weitere Ausgabe(n) nicht angehaengt)" if omitted else ""
                await interaction.edit_original_response(
                    content=(
                        f"Fertig · Seed `{rendered.seed}` · {breite}×{hoehe} · "
                        f"Workflow `{profile_name}` · LoRA `{lora_label}`{suffix}"
                    ),
                    attachments=discord_files,
                )
            except (ComfyError, WorkflowError) as exc:
                LOGGER.warning("Generierung fehlgeschlagen: %s", exc)
                await interaction.edit_original_response(content=f"Generierung fehlgeschlagen:\n```\n{str(exc)[:1700]}\n```")
            except Exception as exc:  # Discord should receive a useful response; full details stay in the log.
                LOGGER.exception("Unerwarteter Fehler bei der Generierung")
                await interaction.edit_original_response(
                    content=f"Unerwarteter Fehler: `{type(exc).__name__}`. Details stehen im Bot-Fenster."
                )
            finally:
                if acquired:
                    await self._queue_leave()
                    self.gpu_slots.release()

        @image_command.autocomplete("workflow")
        async def workflow_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            del interaction
            current = current.casefold()
            return [
                app_commands.Choice(name=f"{name} – {profile.description}"[:100], value=name)
                for name, profile in self.settings.workflows.items()
                if current in name.casefold() or current in profile.description.casefold()
            ][:25]

        @image_command.autocomplete("lora")
        async def lora_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            del interaction
            try:
                loras = await self._list_loras()
            except ComfyError:
                return []
            query = current.casefold()
            special = [
                app_commands.Choice(name="Workflow-Standard beibehalten", value="__default__"),
                app_commands.Choice(name="Keine LoRA", value="__none__"),
            ]
            matches = [filename for filename in loras if query in filename.casefold()]
            choices = [
                app_commands.Choice(
                    name=(filename if len(filename) <= 100 else f"{filename[:97]}..."),
                    value=self._lora_alias(filename),
                )
                for filename in matches[: 25 - len(special)]
            ]
            return special + choices

        @self.tree.command(name="status", description="Prueft Bot, Warteschlange und ComfyUI")
        async def status_command(interaction: discord.Interaction) -> None:
            if not self._channel_allowed(interaction):
                await interaction.response.send_message("Dieser Kanal ist fuer den Bot nicht freigegeben.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                health = await self.comfy.health()
                queue = health.get("queue", {})
                running = len(queue.get("queue_running", [])) if isinstance(queue, dict) else "?"
                pending = len(queue.get("queue_pending", [])) if isinstance(queue, dict) else "?"
                async with self._queue_lock:
                    local_active, local_waiting = self._active, self._waiting
                await interaction.edit_original_response(
                    content=(
                        "Bot und ComfyUI sind erreichbar.\n"
                        f"Bot: {local_active} aktiv, {local_waiting} wartend\n"
                        f"ComfyUI: {running} aktiv, {pending} wartend\n"
                        f"Geprueft: {datetime.now().astimezone():%d.%m.%Y %H:%M:%S %Z}"
                    )
                )
            except ComfyError as exc:
                await interaction.edit_original_response(content=str(exc))


def run_bot(settings: Settings) -> None:
    if settings.discord_token is None:
        raise RuntimeError("DISCORD_TOKEN fehlt.")
    bot = ComfyDiscordBot(settings)
    bot.run(settings.discord_token, log_handler=None)

