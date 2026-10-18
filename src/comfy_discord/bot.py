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
from .ollama import OllamaClient, OllamaError, prepare_embed_text
from .resolutions import (
    RESOLUTION_PRESETS,
    RESOLUTION_PRESETS_BY_VALUE,
    VIDEO_RESOLUTION_PRESETS,
    VIDEO_RESOLUTION_PRESETS_BY_VALUE,
    dimensions_for_megapixels,
)
from .workflow import VideoWorkflowRenderer, WorkflowError, WorkflowRenderer


LOGGER = logging.getLogger(__name__)


class ComfyDiscordBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(
            intents=discord.Intents.none(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.comfy = ComfyClient(settings.comfy_url, settings.generation_timeout_seconds)
        self.ollama = OllamaClient(
            settings.ollama_url,
            settings.ollama_model,
            settings.ollama_timeout_seconds,
        )
        self.renderers = {name: WorkflowRenderer(profile) for name, profile in settings.workflows.items()}
        self.video_renderers = {
            name: VideoWorkflowRenderer(profile)
            for name, profile in settings.video_workflows.items()
        }
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
        await self.ollama.start()
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
        await self.ollama.close()
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

    async def _prepare_lora_slot(
        self,
        value: str | None,
        strength: float | None,
        *,
        slot_name: str,
        allow_default_strength: bool,
    ) -> tuple[str | None, float | None, str | None]:
        if value == "__none__":
            return None, 0.0, None
        if value == "__default__" or value is None:
            if strength is not None and not allow_default_strength:
                raise WorkflowError(f"{slot_name}: Bitte zuerst eine LoRA auswaehlen.")
            label = "Workflow-Standard" if allow_default_strength else None
            if label is not None and strength is not None:
                label = f"{label} ({strength:g})"
            return None, strength, label

        selected = await self._resolve_lora(value)
        if selected is None:
            raise WorkflowError(
                f"{slot_name}: Diese LoRA ist in der laufenden ComfyUI-Installation nicht mehr vorhanden."
            )
        actual_strength = 1.0 if strength is None else strength
        return selected, actual_strength, f"{selected} ({actual_strength:g})"

    async def _lora_autocomplete_choices(
        self,
        current: str,
        *,
        primary: bool,
    ) -> list[app_commands.Choice[str]]:
        try:
            loras = await self._list_loras()
        except ComfyError:
            return []
        query = current.casefold()
        special: list[app_commands.Choice[str]] = []
        if not query:
            if primary:
                special.append(
                    app_commands.Choice(name="Workflow-Standard beibehalten", value="__default__")
                )
            special.append(app_commands.Choice(name="Keine LoRA / Slot leer", value="__none__"))
        matches = [filename for filename in loras if query in filename.casefold()]
        choices = [
            app_commands.Choice(
                name=(filename if len(filename) <= 100 else f"{filename[:97]}..."),
                value=self._lora_alias(filename),
            )
            for filename in matches[: 25 - len(special)]
        ]
        return special + choices

    def _register_commands(self) -> None:
        @self.tree.command(name="text", description="Fragt das lokale Qwen-Modell ueber Ollama")
        @app_commands.describe(
            prompt="Deine Frage oder Anweisung an das lokale Modell",
            system="Optionaler System-Prompt fuer Verhalten oder Rolle",
            temperatur="Kreativitaet von 0 (stabil) bis 2 (variabel)",
            max_tokens="Maximale Laenge der Antwort in Tokens",
        )
        async def text_command(
            interaction: discord.Interaction,
            prompt: app_commands.Range[str, 1, 4000],
            system: app_commands.Range[str, 1, 2000] | None = None,
            temperatur: app_commands.Range[float, 0.0, 2.0] = 0.7,
            max_tokens: app_commands.Range[int, 64, 4096] = 1024,
        ) -> None:
            if not self._channel_allowed(interaction):
                await interaction.response.send_message(
                    "Dieser Kanal ist fuer den Bot nicht freigegeben.",
                    ephemeral=True,
                )
                return
            if len(prompt) > self.settings.max_prompt_length:
                await interaction.response.send_message("Der Prompt ist zu lang.", ephemeral=True)
                return

            await interaction.response.defer(thinking=True)
            position = await self._queue_enter()
            await interaction.edit_original_response(
                content=f"Textauftrag angenommen (Warteschlangenposition: {position})."
            )

            acquired = False
            try:
                await self.gpu_slots.acquire()
                acquired = True
                await self._queue_activate()
                await interaction.edit_original_response(
                    content=f"Ollama erzeugt die Antwort mit `{self.settings.ollama_model}` …"
                )
                reply = await self.ollama.chat(
                    prompt,
                    system_prompt=system,
                    temperature=temperatur,
                    max_tokens=max_tokens,
                )
                metadata: list[str] = []
                if reply.response_tokens is not None:
                    metadata.append(f"{reply.response_tokens} Tokens")
                if reply.total_duration_seconds is not None:
                    metadata.append(f"{reply.total_duration_seconds:.1f}s")
                embed_text, needs_file = prepare_embed_text(reply.content)
                embed = discord.Embed(
                    title=self.settings.ollama_model,
                    description=embed_text,
                    color=discord.Color.blurple(),
                )
                if metadata:
                    embed.set_footer(text=" · ".join(metadata))
                attachments = []
                if needs_file:
                    attachments.append(
                        discord.File(
                            io.BytesIO(reply.content.encode("utf-8")),
                            filename="ollama-antwort.txt",
                        )
                    )
                await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    attachments=attachments,
                )
            except OllamaError as exc:
                LOGGER.warning("Ollama-Textgenerierung fehlgeschlagen: %s", exc)
                await interaction.edit_original_response(
                    content=f"Textgenerierung fehlgeschlagen:\n```\n{str(exc)[:1700]}\n```"
                )
            except Exception as exc:
                LOGGER.exception("Unerwarteter Fehler bei der Ollama-Textgenerierung")
                await interaction.edit_original_response(
                    content=(
                        f"Unerwarteter Fehler: `{type(exc).__name__}`. "
                        "Details stehen im Bot-Fenster."
                    )
                )
            finally:
                if acquired:
                    await self._queue_leave()
                    self.gpu_slots.release()

        @self.tree.command(name="bild", description="Erzeugt Bilder mit ComfyUI")
        @app_commands.describe(
            prompt="Was soll erzeugt werden?",
            negative="Optionaler negativer Prompt; leer behaelt den Workflow-Standard",
            seitenverhaeltnis="Form des Bildes, unabhaengig von der Pixelanzahl",
            megapixel="Bildgroesse von 0.25 bis 2 MP; Standard ist 1 MP",
            seed="-1 fuer zufaelligen Seed",
            bilder="Anzahl der Bilder (1 bis 4)",
            schritte="Sampling-Schritte; leer behaelt den Workflow-Standard",
            cfg="CFG Scale; leer behaelt den Workflow-Standard",
            lora="Installierte LoRA; leer behaelt den Workflow-Standard",
            lora_staerke="LoRA-Staerke; leer behaelt den Workflow-Standard",
            lora_2="Zweite installierte LoRA (optional)",
            lora_2_staerke="Staerke der zweiten LoRA; Standard ist 1",
            lora_3="Dritte installierte LoRA (optional)",
            lora_3_staerke="Staerke der dritten LoRA; Standard ist 1",
            workflow="Workflow-Profil; leer nutzt den Standard",
        )
        @app_commands.choices(
            seitenverhaeltnis=[
                app_commands.Choice(name=preset.image_discord_name, value=preset.value)
                for preset in RESOLUTION_PRESETS
            ]
        )
        async def image_command(
            interaction: discord.Interaction,
            prompt: app_commands.Range[str, 1, 4000],
            negative: app_commands.Range[str, 0, 4000] | None = None,
            seitenverhaeltnis: str = "1:1",
            megapixel: app_commands.Range[float, 0.25, 2.0] = 1.0,
            seed: app_commands.Range[int, -1, 9007199254740991] = -1,
            bilder: app_commands.Range[int, 1, 4] = 1,
            schritte: app_commands.Range[int, 1, 100] | None = None,
            cfg: app_commands.Range[float, 0.0, 30.0] | None = None,
            lora: str | None = None,
            lora_staerke: app_commands.Range[float, 0.0, 2.0] | None = None,
            lora_2: str | None = None,
            lora_2_staerke: app_commands.Range[float, 0.0, 2.0] | None = None,
            lora_3: str | None = None,
            lora_3_staerke: app_commands.Range[float, 0.0, 2.0] | None = None,
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

            preset = RESOLUTION_PRESETS_BY_VALUE.get(seitenverhaeltnis)
            if preset is None:
                await interaction.response.send_message(
                    "Dieses Standardformat ist nicht bekannt.", ephemeral=True
                )
                return
            final_width, final_height = dimensions_for_megapixels(
                preset.width,
                preset.height,
                megapixel,
            )

            final_width, final_height = renderer.normalize_dimensions(
                final_width,
                final_height,
            )

            try:
                if "lora_name" not in renderer.profile.bindings:
                    if any(
                        value is not None
                        for value in (
                            lora,
                            lora_staerke,
                            lora_2,
                            lora_2_staerke,
                            lora_3,
                            lora_3_staerke,
                        )
                    ):
                        raise WorkflowError(
                            f"Der Workflow {profile_name!r} unterstuetzt keine LoRA-Auswahl."
                        )
                    selected_lora = selected_strength = None
                    selected_lora_2 = selected_strength_2 = None
                    selected_lora_3 = selected_strength_3 = None
                    lora_label = lora_label_2 = lora_label_3 = None
                else:
                    selected_lora, selected_strength, lora_label = await self._prepare_lora_slot(
                        lora,
                        lora_staerke,
                        slot_name="LoRA 1",
                        allow_default_strength=True,
                    )
                    selected_lora_2, selected_strength_2, lora_label_2 = await self._prepare_lora_slot(
                        lora_2,
                        lora_2_staerke,
                        slot_name="LoRA 2",
                        allow_default_strength=False,
                    )
                    selected_lora_3, selected_strength_3, lora_label_3 = await self._prepare_lora_slot(
                        lora_3,
                        lora_3_staerke,
                        slot_name="LoRA 3",
                        allow_default_strength=False,
                    )
            except (ComfyError, WorkflowError) as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return

            lora_summary = ", ".join(
                label for label in (lora_label, lora_label_2, lora_label_3) if label is not None
            ) or "keine"

            try:
                rendered = renderer.render(
                    prompt=prompt,
                    negative_prompt=negative,
                    width=final_width,
                    height=final_height,
                    batch_size=bilder,
                    seed=seed,
                    lora_name=selected_lora,
                    lora_strength=selected_strength,
                    lora_2_name=selected_lora_2,
                    lora_2_strength=selected_strength_2,
                    lora_3_name=selected_lora_3,
                    lora_3_strength=selected_strength_3,
                    steps=schritte,
                    cfg_scale=cfg,
                    filename_prefix=f"Discord/{interaction.user.id}/{profile_name}",
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
                sampling_summary = ""
                if schritte is not None:
                    sampling_summary += f" · Schritte `{schritte}`"
                if cfg is not None:
                    sampling_summary += f" · CFG `{cfg:g}`"
                await interaction.edit_original_response(
                    content=(
                        f"Fertig · Seed `{rendered.seed}` · {final_width}×{final_height} · "
                        f"Workflow `{profile_name}`{sampling_summary} · "
                        f"LoRAs `{lora_summary}`{suffix}"
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
            return await self._lora_autocomplete_choices(current, primary=True)

        @image_command.autocomplete("lora_2")
        async def lora_2_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            del interaction
            return await self._lora_autocomplete_choices(current, primary=False)

        @image_command.autocomplete("lora_3")
        async def lora_3_autocomplete(
            interaction: discord.Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            del interaction
            return await self._lora_autocomplete_choices(current, primary=False)

        if self.video_renderers:
            @self.tree.command(name="video", description="Erzeugt ein Video mit MiniMax H3 und ComfyUI")
            @app_commands.describe(
                prompt="Was soll im Video geschehen?",
                seitenverhaeltnis="MiniMax-H3-Videoformat",
                dauer="Gewuenschte Dauer in Sekunden (5 bis 15)",
                seed="-1 fuer einen zufaelligen Seed",
                workflow="Video-Workflow-Profil; leer nutzt den Standard",
            )
            @app_commands.choices(
                seitenverhaeltnis=[
                    app_commands.Choice(name=preset.discord_name, value=preset.value)
                    for preset in VIDEO_RESOLUTION_PRESETS
                ]
            )
            async def video_command(
                interaction: discord.Interaction,
                prompt: app_commands.Range[str, 1, 4000],
                seitenverhaeltnis: str = "16:9",
                dauer: app_commands.Range[int, 5, 15] = 5,
                seed: app_commands.Range[int, -1, 9007199254740991] = -1,
                workflow: str | None = None,
            ) -> None:
                if not self._channel_allowed(interaction):
                    await interaction.response.send_message(
                        "Dieser Kanal ist fuer den Bot nicht freigegeben.",
                        ephemeral=True,
                    )
                    return
                if len(prompt) > self.settings.max_prompt_length:
                    await interaction.response.send_message("Der Prompt ist zu lang.", ephemeral=True)
                    return

                profile_name = workflow or self.settings.default_video_workflow
                renderer = self.video_renderers.get(profile_name or "")
                if renderer is None:
                    available = ", ".join(self.video_renderers)
                    await interaction.response.send_message(
                        f"Unbekannter Video-Workflow. Verfuegbar: {available}",
                        ephemeral=True,
                    )
                    return

                preset = VIDEO_RESOLUTION_PRESETS_BY_VALUE.get(seitenverhaeltnis)
                if preset is None:
                    await interaction.response.send_message(
                        "Dieses Videoformat ist nicht bekannt.",
                        ephemeral=True,
                    )
                    return

                try:
                    rendered = renderer.render_video(
                        prompt=prompt,
                        width=preset.width,
                        height=preset.height,
                        duration_seconds=dauer,
                        seed=seed,
                        filename_prefix=f"Discord/{interaction.user.id}/minimax-h3",
                    )
                except WorkflowError as exc:
                    await interaction.response.send_message(str(exc), ephemeral=True)
                    return

                await interaction.response.defer(thinking=True)
                position = await self._queue_enter()
                await interaction.edit_original_response(
                    content=f"Videoauftrag angenommen (Warteschlangenposition: {position})."
                )

                acquired = False
                try:
                    await self.gpu_slots.acquire()
                    acquired = True
                    await self._queue_activate()
                    await interaction.edit_original_response(
                        content="ComfyUI erzeugt Video und Stereo-Audio …"
                    )
                    files = await self.comfy.generate(rendered.graph)
                    selected = files[: self.settings.max_files_per_message]
                    upload_limit = getattr(interaction.guild, "filesize_limit", 10 * 1024 * 1024)
                    oversized = [item for item in selected if len(item.content) > upload_limit]
                    actual_duration = rendered.frame_count / 24
                    result_summary = (
                        f"Fertig · Seed `{rendered.seed}` · {preset.width}×{preset.height} · "
                        f"{rendered.frame_count} Frames / {actual_duration:.2f}s · "
                        f"Workflow `{profile_name}`"
                    )
                    if oversized:
                        names = ", ".join(item.filename for item in oversized)
                        await interaction.edit_original_response(
                            content=(
                                f"{result_summary}\n"
                                "Das Video ist groesser als das Upload-Limit dieses Discord-Servers. "
                                f"Es liegt im ComfyUI-Output unter `Discord/{interaction.user.id}/minimax-h3` "
                                f"({names})."
                            )
                        )
                    else:
                        discord_files = [
                            discord.File(io.BytesIO(item.content), filename=item.filename)
                            for item in selected
                        ]
                        omitted = len(files) - len(selected)
                        suffix = f" ({omitted} weitere Ausgabe(n) nicht angehaengt)" if omitted else ""
                        await interaction.edit_original_response(
                            content=f"{result_summary}{suffix}",
                            attachments=discord_files,
                        )
                except (ComfyError, WorkflowError) as exc:
                    LOGGER.warning("Videogenerierung fehlgeschlagen: %s", exc)
                    await interaction.edit_original_response(
                        content=f"Videogenerierung fehlgeschlagen:\n```\n{str(exc)[:1700]}\n```"
                    )
                except Exception as exc:
                    LOGGER.exception("Unerwarteter Fehler bei der Videogenerierung")
                    await interaction.edit_original_response(
                        content=(
                            f"Unerwarteter Fehler: `{type(exc).__name__}`. "
                            "Details stehen im Bot-Fenster."
                        )
                    )
                finally:
                    if acquired:
                        await self._queue_leave()
                        self.gpu_slots.release()

            @video_command.autocomplete("workflow")
            async def video_workflow_autocomplete(
                interaction: discord.Interaction,
                current: str,
            ) -> list[app_commands.Choice[str]]:
                del interaction
                current = current.casefold()
                return [
                    app_commands.Choice(
                        name=f"{name} – {profile.description}"[:100],
                        value=name,
                    )
                    for name, profile in self.settings.video_workflows.items()
                    if current in name.casefold() or current in profile.description.casefold()
                ][:25]

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

