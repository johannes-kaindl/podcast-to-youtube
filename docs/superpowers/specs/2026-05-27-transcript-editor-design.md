# Transkript-Editor — Design-Spec

| Status | Datum | Phase | Pfad-Vorgänger |
|---|---|---|---|
| Approved | 2026-05-27 | V1 — Segment-Text-Edits | WebGUI V1 (`feat/webgui` → main, shipped 2026-05-22) |

## 1 · Ziel

Whisper macht regelmäßig Fehler in Eigennamen, Fachbegriffen und Fremdwörtern. Aktuell muss der Nutzer entweder mit Tippfehlern leben oder die gesamte Pipeline neu starten. Der Transkript-Editor erlaubt es, **zwischen Transcribe und Meta** den Text pro Segment zu korrigieren — ohne Re-Transcribe.

Ergebnis: Bessere YouTube-Metadaten (Titel/Beschreibung/Kapitel basieren auf dem Transkript), korrekte SRT-Untertitel im Render, weniger Frust.

## 2 · Scope

### In Scope (V1)

- **Segment-Text-Edits** — pro Segment den `text`-String editieren. Speaker, Timecodes, Word-Level-Timings bleiben unverändert.
- **Opt-in Pause nach Transcribe** — Start-Form-Checkbox `[ ] Pause after transcribe for editing` (default off, persisted in `settings.json`). Pipeline läuft Transcribe → stoppt → Run-Detail zeigt Edit-CTA → User editiert oder skippt → klickt "Continue" → Meta + Render starten.
- **Nachträglich editieren** — solange `<stem>.whisperx.json` existiert: Edit-Link in Run-Detail. Save invalidiert Meta + Render (Status → `pending`), bestehende Click-to-restart-Phase-Mechanik übernimmt den Re-Run.
- **Backup** — bei erstem Save wird `<stem>.whisperx.original.json` einmalig angelegt. Folgende Saves überschreiben nur die Live-JSON.
- **SRT/TXT-Regeneration** — Save schreibt `<stem>.whisperx.json` neu und regeneriert `<stem>.srt` und `<stem>.txt` aus dem editierten Inhalt (gleiche Logik wie `transcribe.py:transcribe()`).
- **Stale-Flag** — editierte Segmente bekommen `_edited: true` (für künftige Sichtbarkeit in der UI / Phase 2). Word-Level-Timings bleiben physisch erhalten, sind aber semantisch stale, wenn der Segment-Text geändert wurde — V1 ignoriert das.

### Out of Scope (Phase 2 oder später)

- Word-Level-Edits (einzelne Wörter mit Timecode anpassen)
- Speaker-Re-Labelling (SPEAKER_00 → "Anna")
- Segment-Merge / Segment-Split
- Word-Timing-Re-Alignment nach Text-Edit
- Diff-View vs. Original
- Undo-Stack / Edit-History
- Bulk-Replace (Find & Replace)
- Re-Diarization-Trigger
- Spell-Check / LLM-Korrektur-Vorschlag

## 3 · Architektur

### 3.1 Datei-Struktur

Additiv — keine bestehende Datei wird gelöscht oder grundlegend umgebaut. Bestehende `--skip-meta --skip-render --skip-upload`-Flags von `pipeline.py` werden für Pause-Logik wiederverwendet (keine `pipeline.py`-Änderung nötig).

```
whisper-pipeline/
├── transcript_editor.py            ← NEU: load_segments, save_edits, regenerate_srt_txt, invalidate_downstream
├── webgui/
│   ├── app.py                      ← +2 Routes: GET /runs/{stem}/edit, POST /runs/{stem}/edit
│   ├── runner.py                   ← spawn_pipeline akzeptiert pause_after_transcribe Flag (→ --skip-meta --skip-render --skip-upload)
│   ├── settings.py                 ← +1 Field: pause_after_transcribe (bool, default false)
│   └── templates/
│       ├── index.html              ← +1 Checkbox im Config-Form
│       ├── run_edit.html           ← NEU: Editor-Page
│       └── _partials/
│           └── edit_cta.html       ← NEU: "Edit Transcript" + "Continue"-Buttons (im run_detail eingebunden)
└── tests/
    ├── test_transcript_editor.py   ← NEU: load, save, backup-once, regenerate, invalidate
    ├── test_webgui_edit_routes.py  ← NEU: GET render, POST save, 404 ohne Transcribe
    └── test_pause_after_transcribe.py  ← NEU: Settings-Flag → Pipeline läuft nur Transcribe
```

### 3.2 Datenmodell

**Transcribe-JSON (`<stem>.whisperx.json`) — Struktur (heute):**

```json
{
  "segments": [
    {
      "start": 0.04,
      "end": 0.24,
      "text": " All right.",
      "words": [...],
      "speaker": "SPEAKER_00"
    },
    ...
  ]
}
```

**Nach V1-Edit:**

```json
{
  "segments": [
    {
      "start": 0.04,
      "end": 0.24,
      "text": "All right.",
      "_edited": true,
      "words": [...],
      "speaker": "SPEAKER_00"
    },
    ...
  ]
}
```

- `_edited: true` wird nur gesetzt, wenn der neue Text vom Original abweicht (verglichen mit `<stem>.whisperx.original.json`).
- `words[]` bleibt unverändert. Es wird nicht versucht, Word-Timings ans neue Text-Layout anzupassen.

**Backup (`<stem>.whisperx.original.json`):**

- Wird einmalig beim ersten Save erzeugt — exakte Kopie der `<stem>.whisperx.json` vor dem ersten Edit.
- Bleibt persistent. Folgende Saves überschreiben sie NICHT.

### 3.3 Lifecycle — opt-in Pause-Flow

1. User wählt Audio + setzt Checkbox `[x] Pause after transcribe for editing` → POST `/api/runs`
2. `runner.py:spawn_pipeline()` baut Command mit `--skip-meta --skip-render --skip-upload`
3. Pipeline läuft Transcribe → schreibt `<stem>.whisperx.json` + SRT/TXT → setzt `run-state.json` `transcribe.status = done`, andere Phasen bleiben `pending`/`skipped`
4. Run-Detail zeigt prominent: **📝 Edit Transcript** (primary CTA) + **Continue without editing** (secondary)
5. User klickt **Edit Transcript** → `/runs/{stem}/edit` öffnet sich
6. Editor zeigt Segment-Liste, User editiert (oder nicht), klickt **Save & Return** oder **Save & Continue**
7. **Save & Return** → schreibt JSON+SRT+TXT, zurück zu Run-Detail, Edit-CTAs bleiben sichtbar
8. **Save & Continue** (oder **Continue without editing**) → triggert POST `/runs/{stem}/phase/meta/start` (bestehende Route) → Meta + Render laufen

### 3.4 Lifecycle — nachträglich-edit-Flow

1. User öffnet Run-Detail eines beliebigen Runs mit `transcribe.status = done`
2. Edit-Link sichtbar: **Edit Transcript** (klein, neben Phase-Indicator)
3. Klick → Editor → User editiert + Save
4. Save invalidiert: `meta.status` und `render.status` werden auf `pending` gesetzt (falls vorher `done`)
   - Falls upload.status `done` → bleibt `done` (Upload betrifft existierendes MP4, nicht Transkript)
   - Falls upload.status `skipped` → bleibt `skipped`
5. Phase-Indicator zeigt Meta/Render als pending → User klickt Phase-Icon → re-startet via bestehende Click-to-restart-Mechanik

### 3.5 Modulgrenzen

**`transcript_editor.py`** — pure-Python, kein FastAPI-Import. Testbar standalone.

```python
def load_segments(json_path: str) -> list[dict]:
    """Returns segments with start/end/text/speaker/words/_edited for UI rendering."""

def save_edits(json_path: str, new_texts: list[str]) -> dict:
    """
    Updates segment texts, sets _edited flag where changed.
    Creates <stem>.whisperx.original.json on first call.
    Regenerates SRT + TXT siblings.
    Returns dict: {edited_count, total_segments, backup_created: bool}
    """

def regenerate_srt_txt(json_path: str) -> tuple[str, str]:
    """(Re-)writes SRT + TXT from JSON. Returns (srt_path, txt_path).
    Same logic as transcribe.py — extracted helper."""

def invalidate_downstream(run_state_path: str) -> list[str]:
    """Sets meta/render phases to pending (if previously done).
    Returns list of invalidated phase names."""

def has_been_edited(json_path: str) -> bool:
    """Returns True if any segment has _edited: true."""
```

**`webgui/app.py`** — 2 neue Routes:

```python
@app.get("/runs/{stem}/edit", response_class=HTMLResponse)
async def run_edit(request, stem):
    # Lädt Segments via transcript_editor.load_segments
    # 404 wenn <stem>.whisperx.json fehlt
    # Rendert run_edit.html

@app.post("/runs/{stem}/edit")
async def run_edit_save(request, stem, ...):
    # Parsed Form-Data (segment_text_0, segment_text_1, ...)
    # transcript_editor.save_edits + invalidate_downstream
    # Query-Param ?continue=1 → Redirect zu POST /runs/{stem}/phase/meta/start
    # Sonst → Redirect zu /runs/{stem}
```

**`webgui/runner.py:spawn_pipeline()`** — bestehende Signatur bekommt `pause_after_transcribe: bool = False`-Parameter. Wenn True: append `--skip-meta --skip-render --skip-upload` an Command.

**`webgui/settings.py`** — bekommt Field `pause_after_transcribe: bool = False`. Persisted in `~/.whisper-pipeline-ui.json`.

### 3.6 UI — Editor-Page (`run_edit.html`)

```
┌─ Edit Transcript: my-episode ──────────────────────┐
│  ← Back to Run                Original backup: ✓   │
│                                                     │
│  Tip: Edit text only. Speaker labels and timecodes │
│       are preserved. Saving invalidates Meta+Render│
│       and they will need to re-run.                 │
│                                                     │
│  ┌─ [00:03 SPEAKER_00] ──────────────────────────┐ │
│  │ ┌─────────────────────────────────────────┐   │ │
│  │ │ Hallo und willkommen zu Signal...       │   │ │
│  │ └─────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ [00:12 SPEAKER_01] ★ edited ─────────────────┐ │
│  │ ┌─────────────────────────────────────────┐   │ │
│  │ │ Heute reden wir über Autopoiesis.       │   │ │
│  │ └─────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────┘ │
│  ...                                                │
│                                                     │
│  [Save & Return]   [Save & Continue]   [Cancel]    │
└─────────────────────────────────────────────────────┘
```

- Read-only Segment-Header: `[mm:ss SPEAKER_id]` (+ optional `★ edited` Badge wenn `_edited: true`)
- Editierbares `<textarea>` pro Segment-Text, auto-grow via CSS (`field-sizing: content` / JS-Fallback)
- Pro Segment ein `<input type="hidden" name="original_text_N">` für Server-side Vergleich (Setzt `_edited` nur bei Diff)
- Footer-Buttons:
  - **Save & Return** → POST → Redirect zu `/runs/{stem}`
  - **Save & Continue** → POST mit `?continue=1` → Save + Redirect zu `/runs/{stem}/phase/meta/start`
  - **Cancel** → Browser-Navigate-Back, kein Save
- Reuse: bestehende `base.html`, `style.css`, Kuro Signal Protocol Tokens

### 3.7 UI — Edit-CTA in `run_detail.html`

Drei sichtbare Zustände, abhängig von `run-state.json` + Pause-Setting:

**A) Run pausiert (Transcribe done, Meta pending, Pause-Flag gesetzt):**
```
┌─ ⏸ Pipeline paused after Transcribe ─┐
│  [📝 Edit Transcript]                  │
│  [▶ Continue without editing]          │
└────────────────────────────────────────┘
```

**B) Run nachträglich editierbar (Transcribe done, kein Pause-State):**
```
[ Phase-Indicator ]   [✎ Edit Transcript]
```

**C) Run editiert (mind. ein Segment hat `_edited: true`):**
```
[ Phase-Indicator ]   [✎ Edit Transcript]   ★ transcript edited
```

### 3.8 Settings & Start-Form

`index.html` — neue Checkbox im Advanced/Config-Block:

```html
<label class="checkbox">
  <input type="checkbox" name="pause_after_transcribe" {{ "checked" if settings.pause_after_transcribe }}>
  Pause after transcribe for editing
</label>
```

Bei POST `/api/runs`: Form-Value wird an `runner.spawn_pipeline(..., pause_after_transcribe=...)` durchgereicht UND in `settings.json` persistiert.

## 4 · Testing

### TDD-Approach

Jeder Task wird zuerst als roter Test geschrieben, dann minimal implementiert, dann grün, dann committed.

### Test-Module

**`tests/test_transcript_editor.py` (~10 Tests):**
- `test_load_segments_returns_text_speaker_times`
- `test_save_edits_updates_text`
- `test_save_edits_sets_edited_flag_when_text_differs`
- `test_save_edits_does_not_set_edited_flag_when_text_same`
- `test_save_edits_creates_backup_on_first_call`
- `test_save_edits_does_not_overwrite_backup_on_second_call`
- `test_save_edits_regenerates_srt`
- `test_save_edits_regenerates_txt`
- `test_invalidate_downstream_resets_meta_render_to_pending`
- `test_invalidate_downstream_leaves_upload_alone`

**`tests/test_webgui_edit_routes.py` (~6 Tests):**
- `test_get_edit_renders_segments`
- `test_get_edit_404_when_transcribe_missing`
- `test_post_edit_save_updates_json`
- `test_post_edit_save_redirects_to_run_detail`
- `test_post_edit_save_with_continue_param_triggers_meta_start`
- `test_post_edit_save_invalidates_downstream_in_runstate`

**`tests/test_pause_after_transcribe.py` (~3 Tests):**
- `test_spawn_pipeline_with_pause_appends_skip_flags`
- `test_settings_persists_pause_flag`
- `test_index_form_pause_checkbox_reflects_settings`

**Fixtures:**
- Erweitere `tests/fixtures/run-states/`: 1 neue Fixture `paused-after-transcribe.json` (Transcribe done, andere pending)
- Erweitere `tests/fixtures/`: 1 neues `sample-transcript.whisperx.json` mit 3 Segments

### Regressions-Check

Bestehende 62 Tests dürfen nicht brechen.

## 5 · Konventionen

- **TemplateResponse:** Starlette 1.0+ Signature (`request, name, context`) wie im Rest des Projekts.
- **HTMX:** Save-Buttons sind reguläre Form-Submits (nicht hx-post) — Editor ist eine eigene Page mit voller Page-Reload-Semantik. Vereinfacht Form-Encoding bei 100+ Segments.
- **Encoding:** UTF-8 überall. JSON wird mit `ensure_ascii=False` geschrieben.
- **Branches:** Feature-Branch `feat/transcript-editor`. Conventional commits.
- **Pfade:** `pipeline_core.resolve_audio_path` Pattern — kein hardcoded absolute Path.

## 6 · Risiken & Mitigationen

| Risiko | Mitigation |
|---|---|
| Sehr lange Transkripte (1000+ Segments) brechen Form-POST | V1: kein expliziter Cap; falls Problem → Phase 2 mit lazy-load / pagination |
| User editiert Transkript während Meta läuft | Editor-POST prüft Slot — wenn `meta.status == running` → 409 mit klarer Message |
| Backup-File wird versehentlich gelöscht | Doku in Editor-Page: "Original backup: ✓ saved"-Banner. Phase 2: Diff-View. |
| Word-Timings sind nach Text-Edit stale → SRT/TXT okay, aber Remotion-Word-Highlight fehl-aligned | V1: Doku-Hint im Editor ("Word-level highlighting in video may be off after edits — fix in Phase 2"). |
| User vergisst Re-Run nach nachträglichem Edit | Phase-Indicator zeigt visuell `pending` → existing UX kümmert sich darum. |

## 7 · Phase-2-Roadmap (separate Spec)

Nicht in V1, hier als Pointer:

1. **Word-Level-Edits** — einzelne Wörter editieren + Re-Align Word-Timings via WhisperX-Align
2. **Speaker-Re-Labelling** — pro Segment Speaker ändern, optional bulk-rename (`SPEAKER_00` → `Anna`)
3. **Merge/Split-Segments** — zwei Segments zusammenführen oder eines in zwei teilen (mit Time-Re-Calc)
4. **Diff-View** — Side-by-side Original vs. Current
5. **Undo-Stack** — Edit-History pro Run, Revert per Segment oder global

Phase 2 baut auf V1-Datenmodell auf (additive Schema-Extensions: `words`-Re-Align, `_speaker_edited`-Flag, `_split_from`/`_merged_with`-Refs).

## 8 · Definition of Done — V1

- [ ] Alle ~19 neuen Tests grün
- [ ] Alle 62 bestehenden Tests bleiben grün
- [ ] Manueller End-to-End Test: Pipeline mit Pause-Flag → Editor → Save & Continue → Meta + Render laufen mit editiertem Transkript
- [ ] Manueller End-to-End Test: Nachträglicher Edit eines abgeschlossenen Runs → Invalidate Meta + Render → Re-Run via Click-to-restart
- [ ] Backup-File wird angelegt und nicht überschrieben
- [ ] `AGENTS.md` aktualisiert (Editor unter "Wo finde ich was", Phase-2-Liste angepasst)
- [ ] Feature-Branch `feat/transcript-editor` → main gemerged (Squash oder regulär, je nach Commit-Anzahl)
