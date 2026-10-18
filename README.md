# ComfyUI Discord Bot

Ein lokaler Discord-Bot, der Slash-Commands in ComfyUI-API-Workflows uebersetzt und erzeugte Bilder oder Videos wieder in Discord hochlaedt.

Zusaetzlich stellt `/text` das lokal installierte Ollama-Modell `huihui_ai/qwen3-abliterated:8b` in Discord bereit. Die Anfrage bleibt auf dem eigenen Rechner; fuer das lokale Modell ist kein Cloud-API-Key erforderlich.

Der Bot ist GPU-unabhaengig: AMD/CUDA/DirectML/ROCm betrifft nur die vorhandene ComfyUI-Installation. ComfyUI sollte separat und lokal unter `127.0.0.1:8188` laufen.

## Enthaltener Krea-2-Workflow

`workflows/krea2_turbo_api.json` wurde aus dem bereitgestellten UI-Workflow als kompakter API-Workflow rekonstruiert. Er entspricht dessen aktivem Bildpfad:

- `krea2_turbo_fp8_scaled.safetensors`
- `qwen3vl_4b_fp8_scaled.safetensors`
- `qwen_image_vae.safetensors`
- aktive `Stylized_Ink_Wash_krea2_3296367_epoch_9.safetensors`-LoRA
- 8 Schritte, Euler, Simple Scheduler, CFG 1.2
- Profil `krea2-turbo`: Prompt-Enhancement aus
- Profil `krea2-turbo-enhanced`: lokales Prompt-Enhancement ueber den eingebauten `TextGenerate`-Node
- optionale `krea2_darkbrush`-LoRA aus

Die Dateien muessen bereits in den passenden `ComfyUI/models/...`-Ordnern liegen. Falls die feste Ink-Wash-LoRA nicht verwendet werden soll, muss Node `51` aus dem API-Workflow entfernt und der `model`-Eingang von Node `3` auf `["10", 0]` gesetzt werden.

## Enthaltener MiniMax-H3-Video-Workflow

`workflows/minimax_h3_t2v_api.json` erzeugt aus einem Textprompt ein MP4-Video mit nativ generiertem Stereo-Audio. Das Profil `minimax-h3-t2v` ist auf die bereits vorhandenen Modelle abgestimmt:

- `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- `minimax_h3_video_vae_fp16.safetensors`
- `minimax_h3_audio_vae_fp32.safetensors`
- `minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors`

Der Workflow verwendet vier Schritte, `res_multistep`, den Simple Scheduler und H.264/MP4. INT8 plus Turbo-LoRA ist fuer die vorhandene AMD/ZLUDA-Installation wesentlich praktikabler als der volle Basis-Workflow. ComfyUI selbst muss aktuell genug sein, damit die nativen Nodes `MiniMaxH3ImageToVideo`, `VAEDecodeAudio`, `CreateVideo` und `SaveVideo` vorhanden sind.

## Enthaltener MOSS-Image-Workflow

`workflows/moss_image_sft_api.json` ist ein vollstaendig lokaler Text-zu-Bild-Workflow fuer die native MOSS-Image-Unterstuetzung in ComfyUI. Das Profil `moss-image-sft` verwendet:

- `moss_image_sft_int8_convrot.safetensors`
- `qwen3.5_9b_w4a8_gptq.safetensors`
- `flux2-vae.safetensors`
- 25 Schritte, `er_sde`, Simple Scheduler, CFG 2.5
- Skip-Layer-Guidance auf Single-Layer 22

Das zusaetzliche Profil `moss-image-sft-enhanced` schaltet vor MOSS denselben lokalen Prompt-Enhancer wie `krea2-turbo-enhanced`. Es verwendet dafuer zusaetzlich `qwen3vl_4b_fp8_scaled.safetensors`, das fuer den vorhandenen Krea-Workflow bereits installiert ist. Der erweiterte Prompt wird anschliessend mit dem separaten MOSS-Textencoder verarbeitet; ein Cloud-Dienst, API-Key oder weiterer Modelldownload ist nicht erforderlich.

Die drei Dateien belegen zusammen ungefaehr 13 GB. Der mitgelieferte Downloader speichert laufende Downloads als `.part`, setzt sie nach Verbindungsabbruechen bytegenau fort und wiederholt temporaere Fehler automatisch:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\download-moss-models.ps1
```

Bei einem Abbruch denselben Befehl einfach erneut ausfuehren. Fuer einen anderen ComfyUI-Ordner kann `-ComfyRoot "X:\Pfad\zu\ComfyUI"` angegeben werden. Die native MOSS-Integration erfordert eine aktuelle ComfyUI-Version; ein Cloud-Dienst oder API-Key wird nicht verwendet.

Fuer einen stillen Hintergrundlauf kann zusaetzlich `-Quiet` gesetzt werden. Dabei zeigt `Get-Item "G:\AI_NEW\comfyui-rocm-091926\models\diffusion_models\*.part"` den aktuellen Stand der Teildatei.

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
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=huihui_ai/qwen3-abliterated:8b
OLLAMA_TIMEOUT_SECONDS=600
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
/text prompt:Erklaere mir in drei Saetzen, was CFG Scale bedeutet
/bild prompt:... seitenverhaeltnis:3:4 Portraet Standard (888x1184) seed:-1 bilder:1
/video prompt:Eine Drohnenfahrt ueber eine neblige Bergstadt seitenverhaeltnis:16:9 dauer:5 seed:-1
```

`/text` sendet den Prompt an den lokalen Ollama-Server. Optional koennen `system`, `temperatur` und `max_tokens` gesetzt werden. Laengere Antworten teilt der Bot automatisch auf mehrere Discord-Nachrichten auf. Ollama muss im Hintergrund laufen; bei der Windows-App geschieht das normalerweise automatisch. Bild-, Video- und Textauftraege teilen sich standardmaessig denselben GPU-Warteschlangenplatz, damit die Modelle nicht gleichzeitig den Grafikspeicher belegen.

Fuer Prompt-Enhancement im Parameter `workflow` je nach Bildmodell `krea2-turbo-enhanced` oder `moss-image-sft-enhanced` auswaehlen. Beide nutzen den bereits installierten Qwen/Krea-Textencoder lokal und benoetigen keinen externen API-Key. Ohne Auswahl wird weiterhin `moss-image-sft` als Standard verwendet.

Fuer MOSS-Image im Parameter `workflow` das Profil `moss-image-sft` auswaehlen. MOSS benoetigt Bildgroessen in 16er-Schritten. Der Bot rundet die vorhandenen Seitenverhaeltnis-Presets fuer dieses Profil automatisch auf das naechste gueltige Raster; Krea-Aufloesungen bleiben unveraendert. Das MOSS-Profil besitzt derzeit keine LoRA-Slots, damit nicht versehentlich inkompatible Krea-LoRAs geladen werden.

Mit `schritte` (1 bis 100) und `cfg` (0 bis 30) lassen sich Sampling-Schritte und CFG Scale fuer jedes Bildprofil pro Auftrag ueberschreiben. Bleiben die Felder leer, nutzt der Bot die im Workflow gespeicherten Werte: MOSS standardmaessig 25 Schritte bei CFG 2.5, Krea standardmaessig 8 Schritte bei CFG 1.2.

`seitenverhaeltnis` bietet dieselben acht 1-Megapixel-Formate wie ComfyUIs `ResolutionSelector`: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `9:16`, `16:9` und `21:9`. Das ausgewaehlte Format ueberschreibt `breite` und `hoehe`. Ohne Auswahl koennen eigene Werte in 8er-Schritten angegeben werden; `breite:888 hoehe:1184` ist daher ebenfalls gueltig.

Beim Parameter `lora` fragt der Bot automatisch `ComfyUI/models/loras` ab und zeigt die aktuell installierten Dateien als Discord-Autovervollstaendigung. `Keine LoRA` setzt die Staerke auf 0; ein leeres Feld oder `Workflow-Standard beibehalten` nutzt die im Workflow hinterlegte LoRA. Mit `lora_staerke` kann ein Wert von 0 bis 2 gewaehlt werden. Nach Aenderungen im LoRA-Ordner wird die Liste innerhalb von 30 Sekunden aktualisiert.

Bis zu drei LoRAs koennen in einem Auftrag verkettet werden. Dafuer `lora`/`lora_staerke`, `lora_2`/`lora_2_staerke` und `lora_3`/`lora_3_staerke` verwenden. Die zusaetzlichen Slots sind standardmaessig deaktiviert; bei ausgewaehlter Datei ist ihre Standardstaerke `1.0`. Benoetigte Trigger-Woerter weiterhin in den Prompt schreiben.

`/video` verwendet MiniMax H3 mit nativem Stereo-Audio. Zur Auswahl stehen H3-gerechte Formate von `1:1` bis `21:9`; Standard ist `1344x768` (`16:9`). Die Dauer kann zwischen 5 und 15 Sekunden liegen. MiniMax richtet sie intern auf sein erforderliches Raster `17k+5` bei 24 fps aus, daher werden beispielsweise aus 5 Sekunden 124 Frames beziehungsweise etwa 5,17 Sekunden. Videoauftraege koennen auf AMD/ZLUDA laenger dauern; `GENERATION_TIMEOUT_SECONDS=3600` ist deshalb empfohlen. Ist eine MP4 groesser als das Upload-Limit des Discord-Servers, nennt der Bot stattdessen ihren Ordner unter `ComfyUI/output/Discord/...`.

ComfyUI darf nicht direkt ins Internet freigegeben werden. Der Discord-Bot baut selbst die ausgehende Verbindung zu Discord auf.

## Konfiguration

`config.json` ordnet die Discord-Parameter konkreten Node-Inputs zu. Bildprofile liegen unter `workflows`, Videoprofile separat unter `video_workflows`. Weitere API-Workflows koennen unter `workflows/` abgelegt und dort als zusaetzliche Profile eingetragen werden.

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

