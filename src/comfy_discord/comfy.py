from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp


class ComfyError(RuntimeError):
    """A concise, user-displayable ComfyUI error."""


@dataclass(frozen=True)
class GeneratedFile:
    filename: str
    content: bytes


class ComfyClient:
    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15, sock_read=None)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("ComfyClient.start() wurde nicht aufgerufen.")
        return self._session

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _ws_url(self, client_id: str) -> str:
        parts = urlsplit(self.base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        base_path = parts.path.rstrip("/")
        return urlunsplit((scheme, parts.netloc, f"{base_path}/ws", urlencode({"clientId": client_id}), ""))

    async def _json_response(self, response: aiohttp.ClientResponse) -> Any:
        text = await response.text()
        if response.status >= 400:
            detail = text[:1500] or response.reason
            try:
                payload = json.loads(text)
                detail = payload.get("error", payload)
            except json.JSONDecodeError:
                pass
            raise ComfyError(f"ComfyUI HTTP {response.status}: {detail}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ComfyError("ComfyUI hat keine gueltige JSON-Antwort geliefert.") from exc

    async def health(self) -> dict[str, Any]:
        try:
            async with self.session.get(self._url("system_stats")) as response:
                stats = await self._json_response(response)
            async with self.session.get(self._url("queue")) as response:
                queue = await self._json_response(response)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise ComfyError(f"ComfyUI ist unter {self.base_url} nicht erreichbar: {exc}") from exc
        return {"stats": stats, "queue": queue}

    async def list_models(self, folder: str) -> list[str]:
        """Return model filenames from ComfyUI's configured model folders."""
        try:
            async with self.session.get(self._url(f"models/{folder}")) as response:
                payload = await self._json_response(response)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise ComfyError(f"ComfyUI-Modelle konnten nicht gelesen werden: {exc}") from exc
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise ComfyError(f"ComfyUI hat fuer models/{folder} eine ungueltige Antwort geliefert.")
        return sorted(payload, key=str.casefold)

    async def generate(self, graph: dict[str, Any]) -> list[GeneratedFile]:
        client_id = str(uuid.uuid4())
        prompt_id: str | None = None
        try:
            async with self.session.ws_connect(self._ws_url(client_id), heartbeat=30) as websocket:
                async with self.session.post(
                    self._url("prompt"),
                    json={"prompt": graph, "client_id": client_id},
                ) as response:
                    queued = await self._json_response(response)
                prompt_id = str(queued.get("prompt_id", ""))
                if not prompt_id:
                    raise ComfyError("ComfyUI hat keine prompt_id zurueckgegeben.")
                await self._wait_for_completion(websocket, prompt_id)
                history = await self._wait_for_history(prompt_id)
        except ComfyError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            where = f" fuer Auftrag {prompt_id}" if prompt_id else ""
            raise ComfyError(f"Verbindung zu ComfyUI fehlgeschlagen{where}: {exc}") from exc

        files = await self._download_outputs(history)
        if not files:
            raise ComfyError("Der Workflow wurde beendet, hat aber keine Datei-Ausgabe geliefert.")
        return files

    async def _wait_for_completion(
        self,
        websocket: aiohttp.ClientWebSocketResponse,
        prompt_id: str,
    ) -> None:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ComfyError(f"Zeitlimit von {self.timeout_seconds} Sekunden ueberschritten.")
            try:
                message = await websocket.receive(timeout=min(5.0, remaining))
            except asyncio.TimeoutError:
                history = await self._get_history(prompt_id)
                if history is not None:
                    self._raise_for_history_error(history)
                    return
                continue

            if message.type is aiohttp.WSMsgType.TEXT:
                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError:
                    continue
                data = payload.get("data", {})
                if str(data.get("prompt_id", "")) != prompt_id:
                    continue
                if payload.get("type") in {"execution_error", "execution_interrupted"}:
                    detail = data.get("exception_message") or data.get("node_type") or payload.get("type")
                    raise ComfyError(f"Workflow fehlgeschlagen: {detail}")
                if payload.get("type") == "executing" and data.get("node") is None:
                    return
            elif message.type in {
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.ERROR,
            }:
                history = await self._get_history(prompt_id)
                if history is not None:
                    self._raise_for_history_error(history)
                    return
                raise ComfyError("ComfyUI hat die WebSocket-Verbindung vorzeitig beendet.")

    async def _get_history(self, prompt_id: str) -> dict[str, Any] | None:
        async with self.session.get(self._url(f"history/{prompt_id}")) as response:
            payload = await self._json_response(response)
        record = payload.get(prompt_id) if isinstance(payload, dict) else None
        return record if isinstance(record, dict) else None

    async def _wait_for_history(self, prompt_id: str) -> dict[str, Any]:
        for _ in range(20):
            history = await self._get_history(prompt_id)
            if history is not None:
                self._raise_for_history_error(history)
                return history
            await asyncio.sleep(0.25)
        raise ComfyError("ComfyUI meldet Abschluss, aber der Verlaufseintrag fehlt.")

    @staticmethod
    def _raise_for_history_error(history: dict[str, Any]) -> None:
        status = history.get("status", {})
        if isinstance(status, dict) and status.get("status_str") == "error":
            messages = status.get("messages", [])
            detail = messages[-1] if messages else "unbekannter Ausfuehrungsfehler"
            raise ComfyError(f"Workflow fehlgeschlagen: {str(detail)[:1500]}")

    async def _download_outputs(self, history: dict[str, Any]) -> list[GeneratedFile]:
        result: list[GeneratedFile] = []
        outputs = history.get("outputs", {})
        if not isinstance(outputs, dict):
            return result
        for output in outputs.values():
            if not isinstance(output, dict):
                continue
            for image in output.get("images", []):
                if not isinstance(image, dict) or "filename" not in image:
                    continue
                params = {
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                }
                async with self.session.get(self._url("view"), params=params) as response:
                    if response.status >= 400:
                        await self._json_response(response)
                    content = await response.read()
                safe_name = PurePath(str(image["filename"])).name
                result.append(GeneratedFile(filename=safe_name, content=content))
        return result

