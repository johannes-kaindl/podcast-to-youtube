# Transkript-Editor Phase 2 — Design-Spec

| Status | Datum | Phase | Pfad-Vorgänger |
|---|---|---|---|
| Approved | 2026-05-27 | Phase 2 — Speaker / Merge-Split / Word-Edits / Diff / Undo | V1 (`feat/transcript-editor` → main, shipped 2026-05-27) |

## 1 · Ziel

Phase 2 erweitert den V1-Editor um fünf Features, die V1 als "Out of Scope" markiert hatte:

1. **Speaker-Re-Labelling** — per-Segment Speaker ändern + Bulk-Rename (`SPEAKER_00` → `Anna`)
2. **Merge/Split-Segments** — zwei Segmente zusammenführen oder eines am Char-Index teilen
3. **Word-Level-Edits** — einzelne Wörter im Word-View editieren (kein Audio-Re-Align in V1)
4. **Diff-View** — Side-by-side Original (`.original.json`) vs Current
5. **Undo-Stack** — pro Save-Aktion ein Snapshot, Revert zum letzten

Ergebnis: Vollständiger Editor-Workflow für alle wesentlichen Whisper-Korrekturen, ohne Re-Transcribe.

## 2 · Scope

### In Scope (Phase 2)

**Speaker-Re-Labelling:**
- Pro-Segment-Dropdown im Editor → Speaker ändern (z.B. `SPEAKER_01` → `SPEAKER_00`)
- Bulk-Rename: Input "Rename `SPEAKER_00` to ___" → alle Vorkommen werden überschrieben
- Per-segment-Change setzt `_speaker_edited: true` (Diarization-Korrektur)
- Bulk-Rename setzt **kein** Flag (reines Display-Renaming, kein Diarization-Fehler)
- SRT (`[SPEAKER_XX]`-Prefix) und TXT (Sektion-Header) werden bei jedem Save regeneriert

**Merge/Split-Segments:**
- Merge: "Merge with next" pro Segment-Footer → `text = curr.text + " " + next.text`; `end = next.end`; `words = curr.words + next.words`; setzt `_merged_from: [N, N+1]` (Original-Indizes vor dem Merge)
- Split: User wählt Char-Position in Textarea → Split-Button → erzeugt zwei Segmente. Times werden linear interpoliert proportional zur Textlänge. Words werden nach Word-Start-Time einem der zwei Hälften zugeordnet. Beide neuen Segmente erben `_split_from: original_index`.
- Beide Operationen sind HTMX-Endpoints → re-rendern den Editor-Bereich in-place.

**Word-Level-Edits:**
- Separater View `/runs/{stem}/edit/words` — pro Wort eine Zeile mit `[start–end] speaker  word  [edit-field]`
- User editiert einzelne Wörter. Save schreibt nur `word`-String + setzt `_edited: true` pro Word.
- Beim Save wird der **Segment-Text aus den Words rekonstruiert** (`" ".join(w["word"] for w in words)`), damit Segment + Words konsistent sind. Segment selbst bekommt **nicht** `_edited` durch Word-Edit (separates Tracking).
- **Kein Audio-Re-Align in Phase 2.** Word-Timings bleiben bei den Original-Werten (potenziell minimal verschoben, OK für Caption-Ducking). Doku-Hinweis: Für frische Timings → Transcribe-Phase neu starten.

**Diff-View:**
- Page `/runs/{stem}/diff` — read-only Side-by-side
- Pro Segment: links Original-Text, rechts Current-Text. Word-Level-Diff via `difflib.SequenceMatcher`.
- Empty-State falls `<stem>.whisperx.original.json` nicht existiert (nie editiert).
- Zeigt Speaker-Änderungen + Merge/Split-Origins.

**Undo-Stack:**
- Jeder schreibende Endpoint (Text-Save, Speaker-Change, Bulk-Rename, Merge, Split, Word-Save) erzeugt **vor** der Mutation einen Snapshot `output/{stem}/snapshots/<unix-ts>.json` (copy von aktuellem `.whisperx.json`).
- `_history[]` im Haupt-JSON wird mit neuem Eintrag erweitert: `{ts, action, snapshot_filename, edited_count_or_metric}`.
- Undo-Button im Editor: zeigt letzte 5 History-Einträge, klick auf einen → restore von Snapshot + entferne alle History-Einträge **danach**.
- Snapshot-Cleanup automatisch: bei `len(snapshots) > 20` werden älteste gelöscht und aus `_history[]` entfernt.

### Out of Scope (Phase 3+)

- WhisperX-basierte Word-Time-Re-Align nach Edit (zu teuer; User kann Transcribe-Phase neu starten)
- Visual word-timing editor (Wellenform mit drag-bar)
- Multi-User-Conflict-Resolution (App ist Single-User)
- Per-segment collaborative editing
- Export-Formate außer SRT/TXT (z.B. VTT, DOCX) — separates Feature
- Find-and-Replace (eventuell Phase 3)
- Spell-Check / LLM-Korrektur-Vorschläge
- Re-Diarization-Trigger

## 3 · Architektur

### 3.1 Datei-Struktur

```
whisper-pipeline/
├── transcript_editor.py            ← V1 — bleibt (load/save/regen/invalidate/has_been_edited)
├── transcript_segment_ops.py       ← NEU: merge_segment, split_segment, change_speaker, bulk_rename_speaker
├── transcript_word_ops.py          ← NEU: load_words_flat, save_word_edits
├── transcript_history.py           ← NEU: snapshot, undo_last, undo_to, list_history, cleanup_snapshots
├── transcript_diff.py              ← NEU: compute_segment_diff (vs .original.json)
├── webgui/
│   ├── app.py                      ← +9 Routes
│   └── templates/
│       ├── run_edit.html           ← Erweitert: Speaker-Dropdown, Merge/Split-Buttons, Undo-Btn, Bulk-Rename-Form
│       ├── run_edit_words.html     ← NEU: word-level view
│       ├── run_diff.html           ← NEU: diff view
│       └── _partials/
│           ├── segment_editor.html ← NEU: HTMX-fragment für 1 Segment (re-render nach merge/split/speaker-change)
│           ├── history_dropdown.html  ← NEU: zeigt _history[] mit Undo-Buttons
│           └── speaker_bulk_form.html ← NEU: Bulk-Rename-Form
└── tests/
    ├── test_transcript_segment_ops.py  ← NEU (~12 Tests)
    ├── test_transcript_word_ops.py     ← NEU (~6 Tests)
    ├── test_transcript_history.py      ← NEU (~8 Tests)
    ├── test_transcript_diff.py         ← NEU (~5 Tests)
    └── test_webgui_phase2_routes.py    ← NEU (~12 Tests)
```

### 3.2 Datenmodell — Schema-Extensions

Alle Erweiterungen sind **additiv**. V1-only-Tests bleiben grün (alte JSONs ohne `_history`, `_split_from`, etc. werden weiter sauber geladen).

```jsonc
{
  "segments": [
    {
      "start": 0.04, "end": 0.24, "text": "Hello.",
      "_edited": true,                  // V1 — text changed vs original
      "_speaker_edited": true,          // NEU — speaker changed (not via bulk-rename)
      "_split_from": 3,                 // NEU — was part of segment[3] before split
      "_merged_from": [1, 2],           // NEU — created by merging segments 1+2
      // _split_from and _merged_from are mutually exclusive
      "words": [
        {
          "word": "Hello.", "start": 0.04, "end": 0.24, "score": 0.5,
          "_edited": true                // NEU — word string changed via word-view
        }
      ],
      "speaker": "Anna"
    }
  ],
  "_history": [                          // NEU — append-only
    {
      "ts": "2026-05-27T10:32:11Z",
      "action": "merge",                 // edit_text | edit_speaker | bulk_rename | merge | split | edit_words
      "snapshot": "snapshots/1716800000.json",
      "metric": "merged 1+2 → 1"         // human-readable summary
    }
  ]
}
```

### 3.3 Operation-Semantik

#### Merge

`merge_segment(json_path, segment_index)`:

- Vorbedingungen: `0 <= segment_index < len(segments) - 1`
- `new_seg.text = curr.text + " " + next.text`
- `new_seg.start = curr.start`
- `new_seg.end = next.end`
- `new_seg.speaker = curr.speaker` (User kann nachher per Speaker-Change anpassen)
- `new_seg.words = curr.words + next.words`
- `new_seg._merged_from = [segment_index, segment_index + 1]`
- Vorhandene Flags von curr (`_edited` etc.) bleiben; `_split_from` wird gelöscht (Mismatch-Vermeidung)
- Liste shrinkt um 1

#### Split

`split_segment(json_path, segment_index, char_position)`:

- Vorbedingungen: `0 < char_position < len(segments[segment_index].text)`
- `text_left = text[:char_position].rstrip()`, `text_right = text[char_position:].lstrip()`
- Beide nonempty erforderlich → sonst `ValueError`
- Time-Split linear interpoliert: `split_time = start + (end - start) * (char_position / len(text))`
  - Wenn Words vorhanden: präziser über erstes Word, dessen `start >= split_time` — splitten zwischen Words statt mitten in einem Word
- `left_seg.end = split_time`, `right_seg.start = split_time`
- Words werden aufgeteilt nach `word.start < split_time`
- Beide Segmente erben `_split_from: original_index_before_split`
- Liste wächst um 1

#### Change Speaker

`change_speaker(json_path, segment_index, new_speaker)`:

- Vorbedingungen: `new_speaker` nichtleer, max. 64 chars
- Wenn `new_speaker == segments[segment_index].speaker` → no-op
- `segments[segment_index].speaker = new_speaker`
- `segments[segment_index]._speaker_edited = True`

#### Bulk-Rename Speaker

`bulk_rename_speaker(json_path, old_name, new_name)`:

- Vorbedingungen: beide nichtleer, max. 64 chars, unterschiedlich
- Alle Segmente mit `speaker == old_name` bekommen `speaker = new_name`
- **Setzt KEIN `_speaker_edited`-Flag** (Display-Rename, kein Diarization-Fix)
- Returns count of renamed segments

#### Save Word-Edits

`save_word_edits(json_path, segment_index, new_words: list[str])`:

- Vorbedingungen: `len(new_words) == len(segments[segment_index].words)`
- Pro Word: wenn `new_words[i] != segments[segment_index].words[i].word` → setze `.word = new` + `._edited = True`
- Nach allen Word-Updates: rekonstruiere `segments[segment_index].text` als `" ".join(w["word"] for w in words)`
- Segment selbst bekommt **nicht** `_edited` (Word-Level ist separates Tracking)

#### Snapshot + Undo

`snapshot(json_path, action: str, metric: str) -> snapshot_path`:

- Erzeugt `output/{stem}/snapshots/<unix_ts>.json` als Copy des aktuellen `.whisperx.json`
- Lädt aktuelles JSON, appendet `_history[]` mit `{ts, action, snapshot, metric}`
- Schreibt JSON zurück
- Falls > 20 Snapshots existieren: lösche ältesten + zugehörigen `_history`-Eintrag
- Returns absolute snapshot path

`undo_last(json_path) -> dict | None`:

- Falls `_history[]` leer → returns None
- Lädt letzten Snapshot (path aus `_history[-1].snapshot`)
- Überschreibt `.whisperx.json` mit Snapshot-Content
- Snapshot-File wird gelöscht
- `_history[-1]` wird gepoppt
- Trigger `regenerate_srt_txt`
- Returns popped history entry

**Wichtig:** Snapshot wird **vor** der Mutation erstellt — sodass der Snapshot den **State vor der Aktion** enthält. Undo restoriert diesen State.

#### Diff

`compute_segment_diff(json_path) -> list[dict]`:

- Lädt `<stem>.whisperx.json` und `<stem>.whisperx.original.json`
- Falls Original nicht existiert: returns `[]` (UI zeigt Empty-State)
- Für jedes Current-Segment matched anhand `_split_from` / `_merged_from` Flags auf Original-Segment(e)
- Pro Match: nutzt `difflib.SequenceMatcher` auf Wortebene → produziert Tags (`equal`, `replace`, `insert`, `delete`)
- Returns list[dict] mit Feldern: `{current_index, original_indices: list[int], text_diff: list[(tag, original, current)], speaker_changed: bool, original_speaker, current_speaker}`

### 3.4 Routes

```python
# Editor extensions (HTMX endpoints — return segment_editor.html partial)
POST /runs/{stem}/edit/speaker          # form: segment_index, speaker
POST /runs/{stem}/edit/bulk-rename      # form: old_name, new_name
POST /runs/{stem}/edit/merge            # form: segment_index
POST /runs/{stem}/edit/split            # form: segment_index, char_position
POST /runs/{stem}/edit/undo             # no form data — pops latest

# Word-level
GET  /runs/{stem}/edit/words            # render run_edit_words.html
POST /runs/{stem}/edit/words            # form: segment_index, word_0, word_1, ...

# Diff
GET  /runs/{stem}/diff                  # render run_diff.html
```

Bestehende V1-Routes (`GET`/`POST /runs/{stem}/edit`) bleiben unverändert.

Jede Mutating-Route triggert vor der Mutation `snapshot()` und **nach** der Mutation `invalidate_downstream()` + `regenerate_srt_txt()` (wie V1).

### 3.5 UI — Editor-Page (run_edit.html, erweitert)

```
┌─ Edit transcript: ep01 ───────────────────────────────┐
│  ← Back · Diff View · Word View · Undo (5 entries ▾)  │
│  Bulk-Rename: [SPEAKER_00 ▾] → [Anna     ] [Rename]   │
│                                                        │
│  ┌─ Segment 0 ─────────────────────────────────────┐ │
│  │ [Speaker ▾: Anna]  00:03 ★ edited                │ │
│  │ ┌──────────────────────────────────────────────┐ │ │
│  │ │ Hello and welcome to Signal.                 │ │ │
│  │ └──────────────────────────────────────────────┘ │ │
│  │ [Merge with next] [Split at cursor] […]          │ │
│  └──────────────────────────────────────────────────┘ │
│  ...                                                   │
│  [Save & Return] [Save & Continue] [Cancel]            │
└────────────────────────────────────────────────────────┘
```

- **Top-Bar:** Links Back, Diff-View-Link, Word-View-Link, Undo-Dropdown
- **Bulk-Rename-Form:** Speaker-Select (Liste aus distinct speakers im Transcript) + Free-Text + Button
- **Per-Segment:** Speaker-Dropdown statt read-only Label, Merge-/Split-Buttons unter dem Textarea
- **Undo-Dropdown:** Zeigt letzte 5 `_history[]`-Einträge mit Klick-zum-Undo (jeder Klick = undo bis zu diesem Punkt zurück; aktuell V1 nur "undo last" — Phase 2 V1: undo_last, Klick auf älteren Eintrag tut nichts oder ist disabled)

**Vereinfachung:** Für Phase 2 V1 nur `undo_last` — der Dropdown zeigt History als read-only Log, der einzige aktive Button ist "Undo last action". Klick auf ältere Einträge ist nicht implementiert (Phase 3).

### 3.6 UI — Word-View (run_edit_words.html)

```
┌─ Edit words: ep01 / Segment 1 ──────────────┐
│  ← Back to editor                            │
│                                              │
│  Segment 1 (Anna, 00:00:00 – 00:00:24):     │
│                                              │
│  [00.04–00.10] Anna  [Hello   ] ★            │
│  [00.12–00.24] Anna  [welcome ]              │
│  [00.30–00.45] Anna  [to      ]              │
│  ...                                         │
│                                              │
│  [Save] [Cancel]                             │
└──────────────────────────────────────────────┘
```

- Segment-Picker (Dropdown oder URL-Param): wähle eines der Segmente
- Pro Word: Read-only Times + Speaker, editierbares Word
- Save: rebuild segment text from words
- Cancel: zurück ohne Save

### 3.7 UI — Diff-View (run_diff.html)

```
┌─ Diff: ep01 ────────────────────────────────────────────┐
│  ← Back · Showing 3 of 10 segments changed              │
│                                                          │
│  Segment 1 (was Segment 1)  ★ speaker changed: 00→Anna  │
│  ┌── Original ─────────┐  ┌── Current ─────────────────┐ │
│  │ Hello and welcom    │  │ Hello and welcome to Signal │ │
│  │ ~~to Signal.~~      │  │ ★★★★★★★★★★★★★★★★★★★★★★★★★★ │ │
│  └─────────────────────┘  └─────────────────────────────┘ │
│                                                          │
│  Segment 2-3 → Segment 2  ☆ merged                       │
│  ┌── Original ─────────┐  ┌── Current ─────────────────┐ │
│  │ Let's dive into     │  │ Let's dive into autopoiesis │ │
│  │ this autopoiesis    │  │ — sounds good to me.        │ │
│  │ thing.              │  │                             │ │
│  │ Sounds good to me.  │  │                             │ │
│  └─────────────────────┘  └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

- Side-by-side. Difflib-Tagging via Inline-`<ins>` / `<del>` Markup
- Speaker-Änderung als Top-Badge
- Merge/Split-Origin als Badge

## 4 · Testing

**~43 neue Tests (Detail-Aufstellung):**

`test_transcript_segment_ops.py` (~12):
- `test_merge_segment_combines_text_and_words`
- `test_merge_segment_extends_end_time`
- `test_merge_segment_sets_merged_from_flag`
- `test_merge_segment_raises_when_no_next`
- `test_split_segment_creates_two_segments`
- `test_split_segment_splits_words_by_time`
- `test_split_segment_interpolates_times`
- `test_split_segment_sets_split_from_flag`
- `test_split_segment_raises_at_boundary_zero`
- `test_change_speaker_sets_flag`
- `test_change_speaker_noop_when_same`
- `test_bulk_rename_speaker_renames_all_matching`
- `test_bulk_rename_speaker_does_not_set_flag`

`test_transcript_word_ops.py` (~6):
- `test_load_words_flat_returns_segment_indexed_words`
- `test_save_word_edits_updates_word_strings`
- `test_save_word_edits_sets_word_edited_flag`
- `test_save_word_edits_rebuilds_segment_text`
- `test_save_word_edits_does_not_set_segment_edited`
- `test_save_word_edits_raises_on_length_mismatch`

`test_transcript_history.py` (~8):
- `test_snapshot_creates_file`
- `test_snapshot_appends_history_entry`
- `test_snapshot_returns_absolute_path`
- `test_undo_last_restores_previous_state`
- `test_undo_last_deletes_snapshot_file`
- `test_undo_last_pops_history_entry`
- `test_undo_last_returns_none_when_empty`
- `test_cleanup_snapshots_keeps_20_newest`

`test_transcript_diff.py` (~5):
- `test_compute_segment_diff_returns_empty_when_no_original`
- `test_compute_segment_diff_marks_text_changes`
- `test_compute_segment_diff_detects_speaker_change`
- `test_compute_segment_diff_handles_merged_segments`
- `test_compute_segment_diff_handles_split_segments`

`test_webgui_phase2_routes.py` (~12):
- `test_post_speaker_change_updates_segment`
- `test_post_speaker_change_returns_segment_partial`
- `test_post_bulk_rename_renames_all_matching`
- `test_post_merge_combines_segments`
- `test_post_split_creates_two_segments`
- `test_post_split_raises_400_on_invalid_position`
- `test_post_undo_restores_previous_state`
- `test_post_undo_returns_partial`
- `test_get_words_renders_per_word_rows`
- `test_post_words_saves_edits`
- `test_get_diff_shows_changed_segments`
- `test_get_diff_empty_state_when_no_original`

**Bestehende 97 Tests müssen grün bleiben.** Target: ~140 Tests.

## 5 · Konventionen

- **TemplateResponse:** Starlette 1.0+ Signature (request first) — unverändert
- **HTMX:** Mutating-Routes returnen `text/html` Partials (`segment_editor.html`) für In-Place-Updates. Klassisches Form-Submit als Fallback (jedes Form hat `action=` + `method=`, HTMX-Attribute additiv)
- **Branches:** `feat/transcript-editor-phase2`
- **Encoding:** UTF-8, `ensure_ascii=False`
- **Snapshot-Dir:** `output/{stem}/snapshots/<unix_ts>.json`. Wird vor erstem Snapshot automatisch erstellt.

## 6 · Risiken & Mitigationen

| Risiko | Mitigation |
|---|---|
| Snapshot-Disk-Bloat bei vielen Edits | Cap auf 20 Snapshots, automatisches Löschen ältester |
| Split mit char_position innerhalb eines Words → kaputter Word-String im Splitresultat | Char-Split arbeitet nur auf segment.text, Word-Split arbeitet auf word.start (zwei separate Logiken). Doku-Hinweis. |
| Bulk-Rename ist destruktiv (kein Per-Segment-Flag) | Undo verfügbar; Snapshot vor Rename. Confirm-Dialog im UI ("Rename N segments?") |
| Word-Text-Rebuild bricht bei Leerzeichen-Edge-Cases | `" ".join(...)` produziert deterministisch — Original-Whitespace geht verloren. Doku-Hinweis. |
| Diff-View bei stark restrukturiertem Transcript (viele Splits/Merges) unleserlich | Tagging zeigt Merge/Split-Origins als Badges. Best-effort matching via `_split_from`/`_merged_from`. |
| `_history` wächst unbegrenzt | Bei Snapshot-Cleanup wird der zugehörige History-Eintrag mit-entfernt → bounded |
| Concurrent Edits (zwei Tabs) → State-Konflikt | 409-Conflict-Check via `_history.last.ts` (If-Match-Header), Phase 2 V1: nur Single-Tab garantieren, Doku-Hinweis |

## 7 · Phase 3 — separate Spec wenn relevant

Nicht in Phase 2:

1. Audio-Re-Align nach Word-Edit
2. Visual word-timing-editor (Wellenform-Drag)
3. Multi-Tab Conflict-Resolution mit If-Match
4. Find-and-Replace mit Preview
5. Undo-to-arbitrary-history-entry (statt nur undo_last)
6. Spell-Check / LLM-Suggestions
7. Export-Formats (VTT, DOCX, JSON-CSV)

## 8 · Definition of Done — Phase 2

- [ ] Alle ~43 neuen Tests grün
- [ ] Alle 97 bestehenden Tests bleiben grün → 140 Total
- [ ] Manueller End-to-End: Speaker-Re-Labelling (per-segment + bulk), Merge, Split, Word-Edit, Undo, Diff-View — alle funktionieren via Browser
- [ ] Snapshot-Cleanup verifiziert (>20 Snapshots → ältester wird gelöscht)
- [ ] `AGENTS.md` aktualisiert (Phase 2 Features dokumentiert, Phase 3 als nächste Out-of-Scope-Liste)
- [ ] Feature-Branch `feat/transcript-editor-phase2` → main gemerged
