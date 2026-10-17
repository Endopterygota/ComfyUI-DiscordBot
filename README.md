# ComfyUI Discord Bot

Ein lokaler Discord-Bot, der Slash-Commands in ComfyUI-API-Workflows uebersetzt und die erzeugten Bilder wieder in Discord hochlaedt.

Der Bot ist GPU-unabhaengig: AMD/CUDA/DirectML/ROCm betrifft nur die vorhandene ComfyUI-Installation. ComfyUI sollte separat und lokal unter `127.0.0.1:8188` laufen.

## Enthaltener Krea-2-Workflow

`workflows/krea2_turbo_api.json` wurde aus dem bereitgestellten UI-Workflow als kompakter API-Workflow rekonstruiert. Er entspricht dessen aktivem Bildpfad:

- `krea2_turbo_fp8_scaled.safetensors`
- `qwen3vl_4b_fp8_scaled.safetensors`
- `qwen_image_vae.safetensors`
- aktive `Stylized_Ink_Wash_krea2_3296367_epoch_9.safetensors`-LoRA
- 8 Schritte, Euler, Simple Scheduler, CFG 1.2
- Prompt-Enhancement aus
- optionale `krea2_darkbrush`-LoRA aus

Die Dateien muessen bereits in den passenden `ComfyUI/models/...`-Ordnern liegen. Falls die feste Ink-Wash-LoRA nicht verwendet werden soll, muss Node `51` aus dem API-Workflow entfernt und der `model`-Eingang von Node `3` auf `["10", 0]` gesetzt werden.

## 1. Discord-App anlegen

1. Im [Discord Developer Portal](https://discord.com/developers/applications) eine Application erstellen.
2. Unter **Bot** einen Bot und Token erzeugen.
3. Unter **OAuth2 > URL Generator** die Scopes `bot` und `applications.commands` waehlen.
4. Als Bot-Berechtigungen mindestens `View Channels`, `Send Messages` und `Attach Files` waehlen und den Bot auf den eigenen Server einladen.
5. In Discord den Entwicklermodus aktivieren und per Rechtsklick die Server-ID kopieren.

Der Bot braucht keinen Message-Content-Intent, da er Slash-Commands verwendet.

## 2. Lokales Setup

In PowerShell im Projektordner:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Danach `.env` bearbeiten:

```env
DISCORD_TOKEN=dein_geheimes_bot_token
DISCORD_GUILD_ID=deine_server_id
COMFYUI_URL=http://127.0.0.1:8188
```

Das Token niemals in Discord posten oder committen.

## 3. Starten

Zuerst die vorhandene AMD-ComfyUI-Installation mit deren funktionierendem Startbefehl starten. Danach:

```powershell
.\scripts\start-bot.ps1
```

In Discord stehen dann zur Verfuegung:

```text
/status
/bild prompt:... seitenverhaeltnis:3:4 Portraet Standard (888x1184) seed:-1 bilder:1
```

`seitenverhaeltnis` bietet dieselben acht 1-Megapixel-Formate wie ComfyUIs `ResolutionSelector`: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `9:16`, `16:9` und `21:9`. Das ausgewaehlte Format ueberschreibt `breite` und `hoehe`. Ohne Auswahl koennen eigene Werte in 8er-Schritten angegeben werden; `breite:888 hoehe:1184` ist daher ebenfalls gueltig.

Beim Parameter `lora` fragt der Bot automatisch `ComfyUI/models/loras` ab und zeigt die aktuell installierten Dateien als Discord-Autovervollstaendigung. `Keine LoRA` setzt die Staerke auf 0; ein leeres Feld oder `Workflow-Standard beibehalten` nutzt die im Workflow hinterlegte LoRA. Mit `lora_staerke` kann ein Wert von 0 bis 2 gewaehlt werden. Nach Aenderungen im LoRA-Ordner wird die Liste innerhalb von 30 Sekunden aktualisiert.

ComfyUI darf nicht direkt ins Internet freigegeben werden. Der Discord-Bot baut selbst die ausgehende Verbindung zu Discord auf.

## Konfiguration

`config.json` ordnet die Discord-Parameter konkreten Node-Inputs zu. Weitere API-Workflows koennen unter `workflows/` abgelegt und dort als zusaetzliche Profile eingetragen werden.

Die Umgebungsvariablen in `.env.example` steuern Server, Kanal-Freigaben, Timeout und Parallelitaet. Fuer eine einzelne GPU ist `MAX_PARALLEL_JOBS=1` empfohlen; ComfyUI verwaltet dahinter seine eigene Queue.

## Pruefen und testen

```powershell
.\.venv\Scripts\python.exe -m comfy_discord --check
.\.venv\Scripts\python.exe -m pytest
```

`/status` prueft spaeter die echte Verbindung zu ComfyUI.

## Windows-EXE

```powershell
.\scripts\build-exe.ps1
```

Das Ergebnis liegt mit einem Zeitstempel unter `dist\ComfyUI-Discord-Bot-*.exe`. Dadurch kann eine neue Version gebaut werden, waehrend die bisherige EXE noch laeuft. `scripts\start-bot.ps1` waehlt automatisch die neueste Version. Die EXE enthaelt den Python-Bot, waehrend `.env`, `config.json` und `workflows/` absichtlich als editierbare Dateien im Projektordner bleiben.

