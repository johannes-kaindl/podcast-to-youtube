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
cd /Users/Shared/20_Claude/26-001-whisper-pipeline
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# Remotion-Dependencies (einmalig)
cd "../10_ObsidianVaults/00_ShadowVault/20-projekte/26-001 Whisper Audio-Transkription Pipeline/05-visuals/Remotion Rendering"
npm install
cd -

# YouTube OAuth (einmalig, braucht echtes Terminal-Fenster)
python auth_youtube.py
```

## TUI (Empfohlen)

```bash
podcast-video-upload              # Alias — TUI startet direkt
podcast-video-upload podcast.m4a  # Audio-Pfad vorausgefüllt
```

Oder ohne Alias:

```bash
source .venv/bin/activate
python tui.py podcast.m4a
```

Zweispaltig: Konfigurationsformular links, Live-Log rechts.

| Taste | Funktion |
|---|---|
| `Ctrl+R` | Pipeline starten |
| `Ctrl+Q` | Beenden |

Felder: Audio-Pfad · Visualizer · Sprache (Standard: Auto) · Modell (Standard: large-v3-turbo) · Sprecher-Erkennung · Episode · Serienname · Schritte überspringen

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

In `~/.zshrc` eingetragen:

```bash
podcast-video-upload [audio.m4a]
```

Aktiviert automatisch die venv, startet `tui.py`, und deaktiviert die venv beim Beenden. Kein `cd` oder `source` nötig.

## YouTube-Kanal wechseln

```bash
rm .youtube_token.pickle
# In YouTube den gewünschten Kanal aktivieren
python auth_youtube.py
```

Aktiver Kanal: `@v6t2b99` (ID: `UCySdF3b7avZ5UH-phJSGtbg`)

## Ausführlichere Dokumentation

→ ShadowVault: `20-projekte/26-001 Whisper Audio-Transkription Pipeline/01-Referenz/`
- `Pipeline-Spezifikation.md` — Architektur, Komponenten, Tech-Stack
- `Betrieb.md` — Runbook, Troubleshooting, häufige Kombinationen
