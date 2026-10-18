from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp


class OllamaError(RuntimeError):
    """Raised when the local Ollama API cannot produce a usable reply."""


@dataclass(frozen=True)
class OllamaReply:
    content: str
    prompt_tokens: int | None
    response_tokens: int | None
    total_duration_seconds: float | None


def prepare_embed_text(text: str, *, limit: int = 4096) -> tuple[str, bool]:
    """Fit an Ollama reply into one embed and signal whether a file is needed."""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned, False

    suffix = "\n\n… Vollstaendige Antwort siehe angehaengte Datei."
    preview_limit = limit - len(suffix)
    cut = max(
        cleaned.rfind("\n", 0, preview_limit + 1),
        cleaned.rfind(" ", 0, preview_limit + 1),
    )
    if cut < preview_limit // 2:
        cut = preview_limit
    return f"{cleaned[:cut].rstrip()}{suffix}", True


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self.timeout_seconds,
                connect=15,
                sock_connect=15,
                sock_read=self.timeout_seconds,
            )
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("OllamaClient.start() wurde nicht aufgerufen.")
        return self._session

    @staticmethod
    def _parse_reply(payload: Any) -> OllamaReply:
        if not isinstance(payload, dict):
            raise OllamaError("Ollama hat keine gueltige JSON-Antwort geliefert.")
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama hat eine leere Antwort geliefert.")

        duration = payload.get("total_duration")
        duration_seconds = duration / 1_000_000_000 if isinstance(duration, int) else None
        prompt_tokens = payload.get("prompt_eval_count")
        response_tokens = payload.get("eval_count")
        return OllamaReply(
            content=content.strip(),
            prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
            response_tokens=response_tokens if isinstance(response_tokens, int) else None,
            total_duration_seconds=duration_seconds,
        )

    async def chat(
        self,
        prompt: str,
        *,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> OllamaReply:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            async with self.session.post(f"{self.base_url}/api/chat", json=body) as response:
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    detail = (await response.text())[:500]
                    raise OllamaError(
                        f"Ollama lieferte HTTP {response.status}, aber kein gueltiges JSON: {detail}"
                    ) from exc
                if response.status >= 400:
                    detail = payload.get("error") if isinstance(payload, dict) else None
                    raise OllamaError(
                        f"Ollama-Fehler HTTP {response.status}: {detail or 'unbekannter Fehler'}"
                    )
                return self._parse_reply(payload)
        except asyncio.TimeoutError as exc:
            raise OllamaError(
                f"Ollama hat nicht innerhalb von {self.timeout_seconds} Sekunden geantwortet."
            ) from exc
        except aiohttp.ClientConnectionError as exc:
            raise OllamaError(
                f"Ollama ist unter {self.base_url} nicht erreichbar. "
                "Bitte Ollama starten und den Befehl erneut versuchen."
            ) from exc
