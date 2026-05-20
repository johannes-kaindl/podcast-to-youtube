# WebGUI für die Whisper-Pipeline — Design-Spec

| Status | Datum | Phase | Pfad-Vorgänger |
|---|---|---|---|
| Draft (Review) | 2026-05-20 | V1 — Single-User, localhost | TUI (`tui_app.py`) |

## 1 · Ziel

Ersetze die bestehende Textual-TUI durch eine browser-basierte WebGUI. Sie deckt alle TUI-Features ab und ergänzt drei Funktionen, die die TUI nicht hat:

1. **Run-Historie / Output-Browser** — Liste aller verarbeiteten Audios mit Status
2. **MP4-Vorschau im Browser** — der Render wird angeschaut, bevor er hochgeladen wird
3. **Manueller Upload-Trigger** — Upload-Phase wird nur auf explizite Bestätigung gestartet (kein Auto-Upload nach Render)

Die WebGUI ist das **neue primäre Interface**. Die TUI bleibt erstmal liegen als Fallback; eine spätere Aufräum-Spec entfernt sie, sobald die WebGUI stabil läuft.

## 2 · Scope

### In Scope (V1)

- TUI-Parität: Audio-Auswahl, Konfiguration (Visualizer / Sprache / Modell / Speakers / Episode / Channel / Skip-Phasen), Pipeline-Start, Live-Log, Progress, Resume-Banner mit `run-state.json`-Logik
- Run-Historie (`runs.html`) mit Filter-Toolbar und Empty-State
- Run-Detail (`run_detail`) mit vier State-Varianten: `running` · `ready-to-upload` · `done` · `aborted`
- MP4-Vorschau via `<video controls>` mit Range-Requests
- Manueller Upload-Trigger mit Privacy-Wahl (Private / Unlisted; Public anwendungsseitig deaktiviert)
- Pre-Flight-Check (abgespeckt): Existing-Output-Check, Disk-Free, Heuristik-ETA
- Reveal-in-Finder + Open-in-QuickTime via Backend-Endpoint (`open -R`, `open -a QuickTime`)
- Status-Mood-Tinting: subtile (~6–8 %) Crimson-Tönung bei aborted Runs, Phosphor-Tönung bei done Runs
- Light/Dark-Toggle (manuell + `prefers-color-scheme`-Default)
- Strategist Spectre als feste Identitäts-Accent (Aspect-Switch nicht in Produktion)
- Confirm-Run-Modal mit „this will happen"-Liste vor dem Pipeline-Start
- Drag-and-Drop für Audio: Pfad-Hint aus Drop-Event, kein File-Upload
- Persistente Logfile pro Run (`output/{stem}/run-{ts}.log`)
- SSE-basierter Live-Log mit Reconnect-Fähigkeit nach Browser-Reload
- Single-Job-Slot — wenn ein Run läuft und ein zweiter gestartet wird, springt die UI auf den laufenden Run

### Out of Scope (Phase 2 oder später)

- Transkript-Editor mit Re-Render-Trigger
- Job-Queue für mehrere Audios in Folge
- Multi-User, Auth, Remote-Zugriff
- Mobile/Tablet-Layout
- Echte Audio-Peaks für Run-Card-Waveforms (V1: prozedural aus `hash(stem)`)
- Aspect-Theme-Switch im Produkt (im Mockup als Tweaks-Layer vorhanden, wird nicht portiert)
- Visual-Regression-Tests
- Tag-/Kategorien-Verwaltung in der UI

## 3 · Architektur

### 3.1 Datei-Struktur

Additiv. Keine bestehende Datei wird gelöscht; `tui_*` ziehen ihre gemeinsamen Helfer aus `pipeline_core.py`.

```
whisper-pipeline/
├── pipeline.py                    ← unverändert
├── transcribe.py · generate_meta.py · render_video.py · upload_youtube.py
│                                  ← unverändert
├── tui_app.py · tui_cmd.py · tui_progress.py · tui.py
│                                  ← bleiben, importieren aus pipeline_core
├── pipeline_core.py               ← NEU: build_command, match_line, state-helpers
├── webgui/                        ← NEU
│   ├── __init__.py
│   ├── app.py                     ← FastAPI-App + Routes
│   ├── runner.py                  ← Subprocess-Wrapper + SSE-Stream
│   ├── runs.py                    ← Output-Verzeichnis-Scan, Run-Historie
│   ├── probe.py                   ← ffprobe-Wrapper, Disk-Free, Existing-Check
│   ├── settings.py                ← Theme/Light-Mode-State (~/.whisper-pipeline-ui.json)
│   ├── templates/
│   │   ├── base.html              ← Topbar, Nav, Theme-Wrapper
│   │   ├── index.html             ← Start/Config-Screen
│   │   ├── runs.html              ← Run-Historie
│   │   ├── run_detail.html        ← Run-Detail (4 State-Varianten)
│   │   └── _partials/
│   │       ├── resume_banner.html
│   │       ├── config_form.html
│   │       ├── phase_indicator.html  ← Stepper-Variante
│   │       ├── progress_bar.html
│   │       ├── log_panel.html
│   │       ├── transcript_preview.html
│   │       ├── metadata_card.html
│   │       ├── upload_card.html
│   │       └── runs_row.html
│   └── static/
│       ├── style.css              ← portiert aus design-concepts/style.css
│       ├── fonts/                 ← vendored woff2 (EB Garamond, Space Grotesk, Inter, JetBrains Mono)
│       └── app.js                 ← SSE-Listener, Modal-Wiring, Tail-Toggle (minimal)
├── webgui.py                      ← NEU: Entry-Point (uvicorn + Browser-Auto-Open)
├── design-concepts/               ← liegt vor, dient als Referenz; nach Integration umziehen oder löschen
└── requirements.txt               ← +fastapi · jinja2 · uvicorn[standard] · sse-starlette · python-multipart
```

### 3.2 Lifecycle

- **Start:** `python webgui.py` oder Alias `podcast-video-upload`. Skript startet `uvicorn webgui.app:app --host 127.0.0.1 --port 8765`, wartet auf Server-Ready, öffnet `http://localhost:8765` im Default-Browser (`webbrowser.open`).
- **Single-Job-Slot:** `webgui.runner` hält in-memory eine Registry mit höchstens **einem einzigen laufenden Subprocess** — egal ob `kind="pipeline"` oder `kind="upload"`. POST /api/runs und POST /runs/{stem}/upload prüfen beide den Slot; falls belegt, geben 409 mit dem stem des laufenden Subprocesses zurück. Während eines Uploads kann also keine neue Pipeline gestartet werden und umgekehrt.
- **Shutdown:** SIGINT/SIGTERM auf den Server triggert sauberes Terminate des Subprocesses. Run-State wird auf `aborted` mit Reason `server-shutdown` gesetzt.

### 3.3 Konventionen

- **Theme** auf `<html data-aspect="gunshi" data-theme="dark|light">`. Default `dark`, von `localStorage` overridden, von `prefers-color-scheme` initial gesetzt.
- **Status-Mood-Tinting:** zusätzliches Attribut `data-page-mood="neutral|success|warning|error"` auf `<body>`. `style.css` definiert je Mood einen subtilen Topbar- und Body-Radial-Tint via `color-mix`. Identitäts-Akzent (`--accent`) bleibt Strategist Spectre.
- **Class-based Components.** Keine Web-Components. Wiederverwendbare Blocks als Jinja-Partials in `_partials/`.

## 4 · Routes

Alle Routes sind localhost-only. Kein CSRF-Schutz im V1 (Single-User, no third-party origins).

| Methode | Pfad | Zweck | Response |
|---|---|---|---|
| GET | `/` | Start-Screen | `index.html` |
| POST | `/api/audio/probe` | Audio-Datei untersuchen | `{ stem, size_bytes, duration_s, format, exists, resume_state, disk_free_bytes, eta_estimate_s }` |
| POST | `/api/runs` | Pipeline starten | `303 → /runs/{stem}` oder `409` falls Slot belegt |
| GET | `/runs` | Run-Historie | `runs.html` |
| GET | `/runs/{stem}` | Run-Detail | `run_detail.html` (Variante nach Status) |
| GET | `/runs/{stem}/stream` | Live-Log via SSE | `text/event-stream` |
| GET | `/runs/{stem}/phases` | HTMX-Fragment: Phase-Indicator | HTML-Partial |
| GET | `/runs/{stem}/progress` | HTMX-Fragment: Progress-Bar | HTML-Partial |
| GET | `/runs/{stem}/preview.mp4` | MP4 mit Range-Support | Video-Stream |
| POST | `/runs/{stem}/upload` | YouTube-Upload starten | `202 Accepted` + SSE-Stream re-attaches |
| POST | `/runs/{stem}/skip-upload` | Upload als skipped markieren | `204` |
| POST | `/runs/{stem}/abort` | SIGTERM auf laufenden Subprocess | `204` |
| POST | `/open/finder` | `open -R <path>` | `204` |
| POST | `/open/quicktime` | `open -a QuickTime <path>` | `204` |
| GET | `/api/settings` | Aktuelle Theme/Mode-Einstellungen | `{ theme: "dark"|"light" }` |
| POST | `/api/settings` | Theme/Mode setzen | `204` |

## 5 · Daten-Modell

### 5.1 `run-state.json` (bestehendes Schema, unverändert)

Wird in `pipeline.py` schon geschrieben. Die WebGUI liest nur — sie schreibt nicht direkt in dieses File während eine Pipeline läuft (das macht der Subprocess).

```json
{
  "schema_version": 1,
  "audio": "/abs/path.m4a",
  "stem": "folge-082",
  "started_at": "2026-05-20T14:02:11Z",
  "updated_at": "2026-05-20T14:09:53Z",
  "config": { /* show_name, episode, language, model, viz_type, diarize, num_speakers, privacy, skip_* */ },
  "phases": {
    "transcribe": { "status": "done|running|aborted|skipped|pending", "started_at": "…", "finished_at": "…", "error": "…", "segments": 412 },
    "meta":       { "status": "…", "title": "…" },
    "render":     { "status": "…", "viz_type": "dialogue", "size_mb": 198.0 },
    "upload":     { "status": "…", "url": "https://youtu.be/…", "privacy": "private" }
  }
}
```

### 5.2 In-Memory Job-Registry

Single instance per server, ein Slot. Wird beim Shutdown geleert.

```python
@dataclass
class ActiveJob:
    stem: str
    audio_path: Path
    output_dir: Path
    process: subprocess.Popen
    log_file: Path
    started_at: datetime
    kind: Literal["pipeline", "upload"]   # zwei mögliche Subprocess-Typen
    queue: asyncio.Queue[StreamEvent]      # für SSE-Subscriber

class JobRegistry:
    _slot: ActiveJob | None
```

### 5.3 SSE Event-Format

Server-Sent Events mit drei Typen:

```
event: log
id: 0042
data: {"ts":"14:09:53","level":"info","msg":"render · frame 4580 / 7386 · 31 fps"}

event: phase
id: 0043
data: {"phase":"render","status":"running","started_at":"…","extra":{"frame":4580,"total":7386}}

event: progress
id: 0044
data: {"value":62,"label":"Render frame 4580 / 7386","eta_s":141}

event: done
id: 0099
data: {"exit_code":0,"kind":"pipeline"}
```

`id` ist eine pro-Run monotone Sequenz, erlaubt Browser-Reconnect via `Last-Event-ID`.

### 5.4 Audio-Probe-Response

```json
{
  "valid": true,
  "stem": "folge-082-die-stille-zwischen-den-zeilen",
  "size_bytes": 49543210,
  "duration_s": 4358,
  "format": "m4a",
  "channels": 2,
  "sample_rate": 48000,
  "resume_state": { /* run-state.json oder null */ },
  "disk_free_bytes": 442381762560,
  "eta_estimate_s": { "transcribe": 194, "meta": 42, "render": 720, "total": 956 }
}
```

Bei `valid: false`: zusätzliches Feld `error` mit String (`file_not_found`, `format_unsupported`, `path_not_absolute`, …).

## 6 · Live-Log und Progress (SSE-Mechanik)

**Vorher: Confirm-Run-Modal.** Das Modal in `index.html` öffnet sich vor POST `/api/runs`. Sein Inhalt wird im Frontend aus der `audio-probe`-Response gebaut (Pre-Flight-Daten aus §9: ETA pro Phase, Disk-Free, Existing-Output-Hint). Der „Start pipeline"-Button im Modal sendet erst POST `/api/runs`.

1. POST `/api/runs` spawnt `python pipeline.py {audio_path} --skip-upload --output-dir {output_dir} …` als Subprocess in `webgui/runner.py`. Registry-Slot wird belegt.
2. Stdout des Subprocesses wird Zeile-für-Zeile von einem Reader-Thread konsumiert. Jede Zeile:
   - wird an die persistente Logfile angehängt: `{output_dir}/run-{ts}.log`
   - wird durch `pipeline_core.match_line(line, current_step)` geschickt — Ausgabe: `LogEvent | PhaseEvent | ProgressEvent | None`
   - wird als `event: log` plus ggf. zusätzlich als `event: phase` / `event: progress` in die `asyncio.Queue` des ActiveJobs eingespeist
3. GET `/runs/{stem}/stream` öffnet eine SSE-Verbindung über `sse-starlette`. Der Endpoint:
   - Falls aktiver Job vorhanden: subscribt an die Queue
   - Falls kein aktiver Job, aber `run-state.json` zeigt `done|aborted`: streamt die persistierte Logfile als `event: log`-Reihe nach, sendet abschließend `event: done` mit dem Exit-Code aus run-state.json, schließt
   - Reconnect-Logik: falls Header `Last-Event-ID` gesetzt, wird das Replay ab `id+1` gestartet
4. Frontend:
   - `EventSource('/runs/{stem}/stream')` in `app.js`
   - `event: log` → eine neue `.row`-Zeile wird an `#log` angefügt; bei `data.level === "error"` wird `.row.error` gesetzt
   - `event: phase` → HTMX-Trigger `htmx.ajax('GET', '/runs/{stem}/phases', {target: '[data-phases-wrapper]', swap: 'outerHTML'})`. Auf dem Server wird der Phase-Strip aus aktuellem `run-state.json` neu gerendert.
   - `event: progress` → analog auf `.progress`
   - `event: done` → HTMX-Trigger auf `GET /runs/{stem}` mit `target: 'body', swap: 'innerHTML'` → führt zu Voll-Refresh in passender Variante
5. **Tail-Toggle** in `.logpanel-head` (existiert im Mockup): Wenn aktiv, scrollt `#log` automatisch zum letzten Eintrag. Wird deaktiviert, sobald User manuell hoch-scrollt; reaktiviert, sobald User wieder ans Ende scrollt.

## 7 · Run-Historie

`webgui/runs.py`:

```python
def list_runs(output_root: Path) -> list[RunSummary]:
    """Scant output_root/*/run-state.json. Sortiert nach updated_at desc."""

@dataclass
class RunSummary:
    stem: str
    started_at: datetime
    updated_at: datetime
    audio_path: str
    show_name: str
    episode: str
    phases: dict[str, PhaseStatus]   # phase → status
    duration_s: int | None            # nur wenn upload.finished_at gesetzt
    video_path: Path | None
    youtube_url: str | None
    waveform_seed: int                # hash(stem) % 2**31
```

Die Run-Historie-Seite (`runs.html`):

- Filter-Chips (`All` · `Done` · `Aborted` · `Unfinished` · `Not uploaded`) sind Links mit `?filter=done`. Server filtert in `list_runs` und liefert das gefilterte Listen-Fragment via HTMX `hx-get`, target `.runs-table tbody`.
- Suche (`<input type="search">`) ist clientseitig — JavaScript filtert auf das DOM, keine Round-Trips. Sollte für ≤ 200 Runs reichen; bei mehr in Phase 2 server-side.
- Empty-State wird gerendert, wenn `list_runs()` leer ist.
- Klick auf eine Row navigiert zu `/runs/{stem}`.

## 8 · MP4-Vorschau und manueller Upload

### 8.1 MP4-Vorschau

- Sobald `phases.render.status === "done"`, rendert `run_detail.html` die `ready-to-upload`-Variante (falls Upload pending).
- `<video controls preload="metadata" src="/runs/{stem}/preview.mp4">` lädt das MP4 mit FastAPI-`FileResponse`. Range-Header-Support via `sse_starlette`-naher `FileResponse`-Erweiterung oder eigene Implementation (`scan_range_header`, `iter_range`).
- Reveal-Buttons triggern via `fetch('/open/finder', {method: 'POST', body: JSON.stringify({path}) })`.

### 8.2 Upload-Workflow

- Privacy-Select default `private` (Public ist disabled auf Frontend- und Backend-Seite).
- Click auf „Upload to YouTube" → POST `/runs/{stem}/upload` mit `{ "privacy": "private" | "unlisted" }`.
- Backend prüft: Registry-Slot frei? Phase `upload` nicht schon done? Render-MP4 existiert? Bei OK: spawnt `python upload_youtube.py {mp4} --privacy private`. Setzt Registry-Slot auf `kind="upload"`.
- Stdout des Upload-Subprocesses geht in dieselbe Run-Logfile (Suffix `-upload`) und wird als SSE-Events weitergegeben.
- Nach Upload-Done schreibt `upload_youtube.py` `phases.upload = { status: "done", url, video_id, privacy }` in `run-state.json`. SSE sendet `event: done {"kind":"upload"}`, Frontend triggert Voll-Refresh → `done`-Variante mit YouTube-URL.
- „Skip upload · keep local" → POST `/runs/{stem}/skip-upload` setzt `phases.upload.status = "skipped"`, kein Subprocess. UI springt direkt in `done`-Variante.

## 9 · Pre-Flight-Check

In `webgui/probe.py`:

- **Existing-Output:** `(output_dir / "run-state.json").exists()` → liefert das State-File mit zurück
- **Disk-Free:** `shutil.disk_usage(output_dir).free`
- **Audio-Probe:** `ffprobe -v error -show_format -show_streams -of json {audio}` (subprocess, 1s Timeout), liefert duration, format, sample_rate, channels
- **ETA-Heuristik:** Pro Phase ein Faktor × duration_s:
  | Phase | Faktor (M-Series-Mac) |
  |---|---|
  | transcribe (large-v3-turbo) | 0.045 |
  | transcribe (large-v3) | 0.18 |
  | meta | konstant 30–60s |
  | render (dialogue) | 0.17 |
  | upload | bandbreite-abhängig, default 0.03 |

Faktoren sind in `webgui/probe.py` als Konstanten. Werden in Phase 2 ggf. aus Run-Historie kalibriert.

## 10 · Status-Mood-Tinting

`<body data-page-mood="…">`-Attribut wird vom Server pro Request gesetzt:

- `/`, `/runs`, `/runs/{stem}` mit phase `running` → `neutral`
- `/runs/{stem}` mit phases `done` und upload `done|skipped` → `success`
- `/runs/{stem}` mit irgendeiner Phase `aborted` → `error`
- `/runs/{stem}` in Resume-State (kein aktiver Prozess, Phase pending) → `warning`

`style.css` definiert pro Mood ein zusätzliches Layer auf der Topbar + Body-Radial:

```css
body[data-page-mood="error"] .topbar {
  background: color-mix(in oklab, var(--role-error) 6%, var(--surface-primary));
}
body[data-page-mood="error"] {
  background:
    radial-gradient(1200px 800px at 70% -20%, color-mix(in oklab, var(--role-error) 8%, transparent), transparent 60%),
    var(--surface-vault);
}
/* ditto für success, warning */
```

Akzent-Tokens (`--accent`, Button-Colors, Link-Colors) bleiben Strategist Spectre. Nur Topbar-BG und Body-Radial werden mood-getönt.

## 11 · Settings

Persistiert in `~/.whisper-pipeline-ui.json`:

```json
{
  "theme": "dark",            // dark | light
  "tail_default": true,       // Auto-Scroll im Log
  "preferred_visualizer": "dialogue",
  "preferred_model": "large-v3-turbo"
}
```

- Lese-Zugriff: GET `/api/settings`
- Schreib-Zugriff: POST `/api/settings` (partial update)
- Default-Werte werden zurückgegeben, wenn die Datei nicht existiert
- Initial-Theme-Setting: client-seitig in `<script>` im `<head>`, prüft `localStorage['theme']` und `prefers-color-scheme` — setzt `data-theme` vor First Paint, um Flash zu vermeiden

## 12 · OS-Hooks

Zwei Endpoints, beide `POST` mit JSON-Body `{ "path": "/abs/path" }`:

- `/open/finder` → `subprocess.run(["open", "-R", path])`, return 204
- `/open/quicktime` → `subprocess.run(["open", "-a", "QuickTime Player", path])`, return 204

Backend prüft, dass `path` innerhalb des Repo-Root oder `output/` liegt (Path-Traversal-Schutz, auch wenn localhost-only).

Buttons im Frontend triggern via `fetch(…, {method: 'POST'})` — kein UI-Feedback bei Erfolg (silent). Bei Fehler eine Toast-Meldung.

## 13 · TUI-Übergang

### 13.1 Extraktion in `pipeline_core.py`

Aus `tui_cmd.py` werden extrahiert:
- `PipelineConfig`-Dataclass
- `build_command(config, pipeline_dir) -> list[str]`
- `resolve_audio_path(raw, pipeline_dir) -> Path`
- `can_diarize() -> bool`
- `is_pyannote_cached() -> bool`

Aus `tui_progress.py` wird extrahiert:
- `match_line(line, current_step) -> ProgressEvent | None`

`pipeline_core.py` hat keine Textual-Dependency. `tui_cmd.py` und `tui_progress.py` werden zu reinen Re-Exports, ihre Funktionen rufen `pipeline_core` auf.

### 13.2 TUI bleibt funktional

`tui.py` startet weiterhin die Textual-App. Nichts an der TUI-UX ändert sich. Sie ist während des V1-Builds Fallback und Vergleichsbasis.

### 13.3 Aufräumung später

Sobald die WebGUI mindestens eine Woche im täglichen Einsatz war und kein wichtiges TUI-Feature fehlt, wird eine separate Spec (`docs/superpowers/specs/YYYY-MM-DD-tui-removal-design.md`) das Entfernen aller `tui_*`-Dateien beschreiben, einschließlich Aktualisierung des README + Alias.

## 14 · Testing

### 14.1 Unit-Tests

- `pipeline_core.match_line()` — Fixtures aus realen Pipeline-Logs (eine pro Phase), prüft Klassifikation und Progress-Extraction. ≥ 12 Fixtures.
- `webgui/runs.py:list_runs()` — Fixture-Verzeichnis mit 6 fingierten `run-state.json`-Dateien (done · running · aborted · skipped-upload · partial-resume · empty). Sortierung, Filtering, Schema-Validation.
- `webgui/probe.py:audio_probe()` — Echte ffprobe-Calls auf Test-Audio-Snippet, plus Mock-Tests für Failure-Pfade.
- `webgui/settings.py` — Load, Save, Default-Values.

### 14.2 Integration

- FastAPI-`TestClient` für jeden Endpoint:
  - GET `/`, `/runs`, `/runs/{stem}` rendern erwartete Templates
  - POST `/api/audio/probe` mit gültiger/ungültiger Datei
  - POST `/api/runs` startet Mock-Subprocess (Mock-`pipeline.py`, die ein vorgefertigtes Stdout-Skript abspielt)
  - GET `/runs/{stem}/stream` liefert Event-Stream, prüft `event: log` / `event: phase` / `event: done`
  - POST `/runs/{stem}/upload` triggert Mock-Upload-Subprocess
  - 409 wenn zweiter Run gestartet wird während Slot belegt
  - `/open/finder` und `/open/quicktime` werden gemockt (kein echter `subprocess.run`)

### 14.3 Manuelles Smoke-Testing

- Vor Merge: ein kompletter Run mit echter Pipeline auf einem Test-Audio (5 Min, 2 Sprecher)
- Reconnect-Test: Mid-Run Browser-Tab schließen, neu öffnen, Log + Phase wiederfinden
- Resume-Test: laufenden Server kill, neu starten, Run-State zeigt aborted, Resume-Banner aus Skip-Checkboxes

### 14.4 Was NICHT getestet wird

- End-to-End mit echter Pipeline (zu teuer und langsam)
- Visual Regression (Mockups sind manuelle Referenz)
- Browser-Cross-Compatibility (Single-User-Mac, Default-Browser, Chrome/Safari aktuelle Versionen)

## 15 · Implementation-Reihenfolge

Empfohlene Schritte fürs writing-plans-Skill:

1. **`pipeline_core.py` extrahieren** + bestehende `tui_*`-Tests grün halten
2. **FastAPI-Skelett** mit Templates aus `design-concepts/` portiert — alle Routes als Stubs, statische Seiten
3. **`webgui/probe.py`** — Audio-Probe + Disk-Free + ETA-Heuristik
4. **`webgui/runs.py`** — Run-Historie scanner, `runs.html` mit echten Daten
5. **`webgui/runner.py`** — Subprocess-Lifecycle + SSE-Stream (zunächst nur log-Events, ohne phase/progress)
6. **`pipeline_core.match_line()`** voll integrieren — `phase`- und `progress`-Events fließen
7. **Run-Detail-States**: running → done-Transition via Voll-Refresh, dann ready-to-upload, dann aborted
8. **Upload-Workflow** — Manuelle Upload-Card + zweiter Subprocess
9. **OS-Hooks** Reveal-in-Finder, Open-in-QuickTime
10. **Mood-Tinting**, Light/Dark-Toggle, Settings-Persistenz
11. **Dev-Smoke-Test** mit echtem Audio, Fixes
12. **README-Update** (TUI bleibt erwähnt; WebGUI als primärer Einstieg) + Alias `podcast-video-upload` zeigt auf `webgui.py`

## 16 · Risiken und offene Punkte

| Risiko | Mitigation |
|---|---|
| SSE-Reconnect-Logik subtil — falsche `Last-Event-ID`-Handhabung führt zu Duplikat-Log-Lines oder Lücken | Persistierte Logfile ist Truth-Source; Reconnect liest aus Datei, nicht aus Memory. Sequence-IDs sind pro Logfile lokal monoton. |
| FastAPI Range-Requests für MP4 nicht out-of-box optimal — große Files (200 MB) können Lade-Latenz haben | Eigene `iter_range`-Implementation mit 1 MB-Chunks; `Cache-Control: no-cache` für Run-MP4s. |
| Single-Job-Slot zu restriktiv — User vergisst Run und kann nicht starten | UI muss laufenden Slot prominent zeigen (Topbar-Pill „Running") + „Open running run"-Link. 409-Response liefert stem für Frontend-Redirect. |
| Page-Mood-Tinting kann visuell zu schwach oder zu stark sein | 6–8 % `color-mix` als Startwert. Dev-Smoke-Test bestätigt, dass es subtil aber wahrnehmbar ist. Token in `style.css` als `--mood-tint-strength`, zentral justierbar. |
| Pre-Flight-ETA-Faktoren ungenau für andere Hardware | Faktoren sind Konstanten in `probe.py`. In Phase 2 aus Run-Historie kalibriert. |
| Drag-and-Drop für Pfad: Browser-API gibt File-Path nicht zuverlässig | Fallback: Drop löst nur visuellen Highlight aus + Hinweis-Text „Pfad einfügen". Manueller Pfad-Eingabe ist primärer Workflow. |
| Mockup-CSS ist 70 KB — größer als typisches V1-CSS | Portierung 1:1; ggf. später Tree-Shaking falls nötig. 70 KB unkomprimiert ist auf localhost vernachlässigbar. |
| Aspect-Theme-Switch wird im Mockup gezeigt, aber nicht ins Produkt portiert — könnte verwirren | `tweaks.js` wird im Production-Build nicht gebundlet. Mockup-Files bleiben als Referenz, der Aspect-Switcher ist nicht in Templates. |

## 17 · Definition of Done

- Alle Routes aus §4 implementiert und durch Unit/Integration-Tests gedeckt
- Vier Run-Detail-Varianten (running · ready-to-upload · done · aborted) im Browser sichtbar, mit echtem Pipeline-Lauf
- Resume-Banner zeigt korrekten State nach Subprocess-Kill und Server-Restart
- MP4-Preview spielt im Browser, Reveal-in-Finder öffnet Finder
- Manueller Upload-Trigger startet `upload_youtube.py`, Logs streamen weiter, YouTube-URL erscheint
- Single-Job-Slot blockt zweite Starts, 409-Antwort enthält stem
- Light/Dark-Toggle persistiert
- Mood-Tinting auf aborted Run sichtbar (subtil)
- `podcast-video-upload`-Alias öffnet WebGUI im Default-Browser
- README aktualisiert: WebGUI als primärer Einstieg, TUI als Fallback erwähnt
- TUI funktioniert weiterhin nach `pipeline_core`-Extraktion
