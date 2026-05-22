# Podcast-zu-YouTube Pipeline

Vollautomatische Pipeline: Audio (.m4a/.mp3/.wav) → Transkript → Metadaten → MP4 → YouTube (Privat).
Läuft vollständig lokal (WhisperX + MLX-Server). Kein Cloud-API-Call außer dem YouTube-Upload selbst.

## Voraussetzungen

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Node.js (für Remotion)
- ffmpeg (`brew install ffmpeg`)
- MLX-Server auf Port 8080 (`launchctl list ai.mlx.mlx-lm-server`)
- Google Cloud: YouTube Data API v3 + `client_secrets.json` (Desktop App)

## Setup

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# Remotion-Dependencies (einmalig)
cd visualizer && npm install && cd ..

# YouTube OAuth (einmalig, braucht echtes Terminal-Fenster)
python auth_youtube.py

# Playlist-Auto-Assignment (optional)
cp playlists.example.json playlists.json   # danach echte Playlist-IDs eintragen
```

## WebGUI (Empfohlen)

```bash
podcast-video-upload                 # Alias — startet WebGUI + öffnet Browser
# oder ohne Alias:
python webgui.py
```

Im Browser auf `http://localhost:8765`. Drop deinen Podcast in die Source-Zone (oder Pfad eingeben),
Optionen wählen, **Start pipeline** klicken. Live-Log + Phase-Progress per Server-Sent Events.

Nach dem Render-Schritt zeigt die WebGUI die MP4-Vorschau direkt im Browser — Upload wird **nicht
automatisch gestartet**. Privacy wählen (Private/Unlisted), dann **Upload to YouTube** klicken.

| Taste | Funktion |
|---|---|
| `Ctrl+R` | Start-Pipeline-Modal öffnen |

Felder: Audio-Pfad · Visualizer · Sprache · Modell · Sprecher-Erkennung · Episode · Channel/Serie · Skip-Phasen

## TUI (Fallback)

Die alte Textual-TUI bleibt erstmal als Fallback verfügbar (gleiche Pipeline, anderes Frontend):

```bash
python tui.py podcast.m4a
```

## Nutzung (CLI)

```bash
source .venv/bin/activate

# Vollständig (Transkription → Meta → Render → Upload)
python pipeline.py podcast.m4a

# Ohne Upload
python pipeline.py podcast.m4a --skip-upload

# Dialogue-View: Teleprompter links + Ring rechts — ideal für Gespräche
python pipeline.py podcast.m4a --viz dialogue --skip-upload

# Monologue-View: zentrierter Ring + Karaoke-Caption
python pipeline.py podcast.m4a --viz monologue --skip-upload

# Mit Speaker-Diarization (nach Akzeptanz der pyannote-Terms auf huggingface.co)
python pipeline.py podcast.m4a --hf-token $HF_TOKEN

# Alle Optionen
python pipeline.py --help
```

Output: `output/<dateiname>/`
- `<stem>.whisperx.json` — Word-level Transkript mit Speaker-Labels
- `<stem>.srt` — Untertitel
- `<stem>.txt` — Plaintext-Transkript
- `<stem>.youtube-meta.json` — Titel, Beschreibung, Tags, Kapitel
- `<stem>-<viz>.mp4` — Fertiges YouTube-Video (1920×1080, 30fps); `<viz>` = waveform | ring | dialogue | monologue

## Schritte einzeln

| Script | Zweck |
|---|---|
| `tui.py` | Interaktives TUI (empfohlener Einstieg) |
| `pipeline.py` | CLI-Orchestrierung aller vier Schritte |
| `transcribe.py` | WhisperX: Audio → JSON/SRT/TXT |
| `generate_meta.py` | MLX-LLM: Transkript → YouTube-Metadaten |
| `render_video.py` | Remotion: Audio + JSON → MP4 (waveform/ring/dialogue/monologue) |
| `upload_youtube.py` | YouTube Data API v3: MP4 → Privates Video |
| `auth_youtube.py` | Einmalige OAuth-Autorisierung |
| `download_models.py` | Alle Modelle vorab herunterladen (Offline-Betrieb) |

## Konfiguration

| Datei | Inhalt |
|---|---|
| `client_secrets.json` | Google OAuth Credentials (nicht committet) |
| `.youtube_token.pickle` | Gecachter OAuth-Token (nicht committet) |
| `.env` | Optionale Env-Variablen |

Umgebungsvariablen:
- `MLX_BASE_URL` — Standard: `http://localhost:8080/v1`
- `MLX_MODEL` — Standard: `mlx-community/Qwen3.6-35B-A3B-4bit`
- `HF_TOKEN` — HuggingFace-Token für Speaker-Diarization

## Offline-Setup (einmalig)

Alle Modelle vorab herunterladen — danach läuft die Pipeline ohne Internet (außer Upload):

```bash
# Whisper + Alignment-Modelle (de, en)
python download_models.py

# + Speaker-Diarization (braucht HF-Token + akzeptierte pyannote-Terms)
python download_models.py --hf-token $HF_TOKEN

# Cache-Status anzeigen
python download_models.py --status
```

## Shell-Alias

In `~/.zshrc` eintragen:

```bash
alias podcast-video-upload='cd /pfad/zu/whisper-pipeline && source .venv/bin/activate && python webgui.py'
```

Aktiviert automatisch die venv und startet die WebGUI im Default-Browser.

## YouTube-Kanal wechseln

```bash
rm .youtube_token.pickle
# In YouTube den gewünschten Kanal aktivieren
python auth_youtube.py
```

Der aktive Kanal wird beim OAuth-Login bestimmt — beim Login den gewünschten YouTube-Kanal auswählen.

## Lizenz

[GNU Affero General Public License v3.0](LICENSE) — Copyright © 2026 jkaindl
