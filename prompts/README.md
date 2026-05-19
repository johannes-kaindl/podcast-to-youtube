# Pipeline-Prompts

Alle LLM-Prompts, die von der Pipeline an MLX gesendet werden, liegen hier als Markdown-Dateien — damit sie ohne Code-Edit getweakt werden können.

## Dateien

| Datei | Wird verwendet von | Rolle |
|---|---|---|
| `meta-system.md` | `generate_meta.py` | System-Role: Stil-Regeln + Format-Constraints |
| `meta-generation.md` | `generate_meta.py` | User-Prompt: konkrete Daten + JSON-Schema |

## Aufbau

Jede Datei beginnt mit einer optionalen YAML-Frontmatter (zwischen `---`-Zeilen), gefolgt vom eigentlichen Prompt-Text. Der Loader (`_load_prompt` in `generate_meta.py`) strippt die Frontmatter und liefert nur den Body — die Frontmatter dient nur als Editor-Hilfe.

```yaml
---
purpose: ...
last-tuned: YYYY-MM-DD
notes: |
  Mehrzeiliger Hinweis...
  Placeholder: {name1}, {name2}, ...
---

Eigentlicher Prompt-Text mit {placeholder}-Platzhaltern
```

## Placeholder

Beide Prompts werden mit `str.format()` gefüllt — die Placeholder müssen exakt so heißen wie in `generate_meta.py` definiert. Aktuelle Liste:

- `{show_name}`, `{episode}`, `{duration_min:.0f}`, `{language_name}`, `{language_code}`, `{transcript}` — nur in `meta-generation.md`
- `{language_name}` — auch in `meta-system.md`

Beim Editieren also: keine Platzhalter erfinden ohne Code-Anpassung, keine doppelten `{}` außer in den literalen JSON-Beispielen (dort steht `{{...}}` damit `.format()` die geschweiften Klammern als Literal behandelt).

## Tweaks ausprobieren

```bash
cd /Users/Shared/20_Claude/26-001-whisper-pipeline
source .venv/bin/activate

# Smoke-Test gegen existierendes Transcript (kein Render, kein Upload)
python generate_meta.py output/test-30s/test-30s.txt \
  --whisperx output/test-30s/test-30s.whisperx.json
```

Output landet in `output/test-30s/test-30s.youtube-meta.md` — direkt vergleichbar.

## Häufige Anpassungen

- **Stil entspannen / Marketing reduzieren** → `meta-system.md`, „VERBOTEN"-Liste erweitern
- **Beschreibungslänge ändern** → `meta-system.md`, „LÄNGEN-Constraints"-Block
- **JSON-Schema erweitern** (neues Feld) → `meta-generation.md` Schema-Block + Code in `format_description_with_chapters` (für Description-Rendering)
- **Temperatur / max_tokens** → nicht hier, sondern direkt in `generate_meta.py` (Funktion `generate_metadata`, Aufruf `mlx_chat(...)`)
