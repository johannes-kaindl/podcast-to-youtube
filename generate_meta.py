#!/usr/bin/env python3
"""
YouTube-Metadaten aus Transkript generieren (via lokalem MLX-Server).
Gibt Episodentitel, Beschreibung, Kapitelmarken und Tags zurück.
Benötigt mlx_lm.server auf Port 8080 (OpenAI-kompatible API).

Usage:
  python generate_meta.py transcript.txt --whisperx transcript.whisperx.json
  python generate_meta.py transcript.txt --show-name "KSP Podcast" --episode "EP 01"
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


MLX_BASE_URL = os.environ.get("MLX_BASE_URL", "http://localhost:8080/v1")
MLX_MODEL = os.environ.get("MLX_MODEL", "mlx-community/Qwen3.6-35B-A3B-4bit")

# Prompts liegen als Markdown unter prompts/ — damit sie ohne Code-Edit
# getweakt werden können (siehe prompts/README.md). Optional-Frontmatter
# zwischen ---/--- wird beim Laden entfernt; der Rest geht als Prompt-Text
# unverändert raus (str.format() füllt {placeholder}).
PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end >= 0:
            raw = raw[end + len("\n---\n"):]
    return raw.strip()


SYSTEM_PROMPT = _load_prompt("meta-system")
GENERATION_PROMPT = _load_prompt("meta-generation")


LANGUAGE_NAMES = {
    "de": "Deutsch",
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "ja": "日本語",
    "zh": "中文",
    "ko": "한국어",
    "ar": "العربية",
    "tr": "Türkçe",
    "sv": "Svenska",
}


def mlx_chat(system: str, user: str, temperature: float = 0.3,
             max_tokens: int = 2048) -> str:
    payload = {
        "model": MLX_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.8,
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        f"{MLX_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    # 900s (15 min) Timeout — bei langen Transkripten (40+ min Audio mit ~700
    # Segmenten) braucht Qwen3.6-35B-A3B-4bit auf Apple Silicon mehrere Minuten
    # bis First-Token + Generation. 300s war zu knapp und führte zu TimeoutError.
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        print(f"FEHLER: MLX/OpenClaw-Server nicht erreichbar ({MLX_BASE_URL}): {e}")
        print("Bei OpenClaw-Gateway: Service-Status prüfen + ggf. neu starten.")
        sys.exit(1)


def parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    # Markdown-Wrapper entfernen
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```\s*$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()
    # strict=False erlaubt rohe Control-Chars (\n, \t) in JSON-Strings —
    # LLM-Output enthält die regelmäßig (z.B. Newlines im description-Feld),
    # was strikter JSON-Parser sonst als "Invalid control character" ablehnt.
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        # Fallback: letzten geschweifte-Klammer-Block extrahieren
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                return json.loads(m.group(0), strict=False)
            except json.JSONDecodeError:
                pass
        # Letzte Rettung: Raw-Response für Debugging persistieren
        debug_path = os.path.join(os.path.dirname(__file__), ".last-failed-meta-response.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(raw)
        raise ValueError(
            f"Kein valides JSON in Antwort. Raw-Output gespeichert: {debug_path}\n"
            f"Erste 600 Zeichen:\n{raw[:600]}"
        )


def estimate_duration(whisperx_path: str | None, txt_path: str) -> float:
    if whisperx_path and os.path.exists(whisperx_path):
        with open(whisperx_path, encoding="utf-8") as f:
            data = json.load(f)
        segs = data.get("segments", [])
        if segs:
            return segs[-1]["end"] / 60
    with open(txt_path, encoding="utf-8") as f:
        words = len(f.read().split())
    return words / 150


def build_chapters_from_whisperx(whisperx_path: str) -> list[dict]:
    with open(whisperx_path, encoding="utf-8") as f:
        data = json.load(f)
    segs = data.get("segments", [])
    if not segs:
        return []
    chapters = [{"time": "00:00", "title": "Intro"}]
    last = 0
    for seg in segs:
        if seg["start"] - last >= 300:
            m, s = divmod(int(seg["start"]), 60)
            chapters.append({"time": f"{m:02d}:{s:02d}", "title": "—"})
            last = seg["start"]
    return chapters


CHAPTERS_HEADER = {
    "de": "KAPITEL",
    "en": "CHAPTERS",
    "fr": "CHAPITRES",
    "es": "CAPÍTULOS",
    "it": "CAPITOLI",
    "pt": "CAPÍTULOS",
    "nl": "HOOFDSTUKKEN",
    "pl": "ROZDZIAŁY",
    "ru": "ГЛАВЫ",
    "ja": "チャプター",
    "zh": "章节",
    "ko": "챕터",
    "ar": "الفصول",
    "tr": "BÖLÜMLER",
    "sv": "KAPITEL",
}


# Transparenz-Footer — am Ende der Description vor den Hashtags.
# Anpassen wenn sich Workflow oder Homepage-URL ändern. Sprache-Fallback: en.
HOMEPAGE_URL = "https://uplink.jkaindl.de"

CREDITS_FOOTER = {
    "de": (
        "━━━ TRANSPARENZ ━━━\n"
        "Audiospur generiert mit NotebookLM (Google).\n"
        "Transkript & Video aus lokaler Pipeline (WhisperX + Remotion).\n\n"
        f"Mehr Infos: {HOMEPAGE_URL}"
    ),
    "en": (
        "━━━ TRANSPARENCY ━━━\n"
        "Audio generated with NotebookLM (Google).\n"
        "Transcript & video produced by a local pipeline (WhisperX + Remotion).\n\n"
        f"More info: {HOMEPAGE_URL}"
    ),
}


def format_description_with_chapters(meta: dict) -> str:
    lang = meta.get("language", "de")
    desc = meta["description_hook"] + "\n\n"
    desc += meta["description_full"] + "\n\n"
    if meta.get("chapters"):
        header = CHAPTERS_HEADER.get(lang, "CHAPTERS")
        desc += f"━━━ {header} ━━━\n"
        for ch in meta["chapters"]:
            desc += f"{ch['time']} {ch['title']}\n"
        desc += "\n"
    # Transparenz-Footer — vor den Hashtags
    desc += CREDITS_FOOTER.get(lang, CREDITS_FOOTER["en"]) + "\n\n"
    if meta.get("hashtags"):
        desc += " ".join(meta["hashtags"])
    return desc.strip()


# Post-Upload-Checkliste — manuelle YouTube-Studio-Schritte. Wird ans Ende
# der .youtube-meta.md gehängt, damit nach jedem Upload eine abhakbare
# Liste bereitsteht. Lifecycle: nach Upload öffnen, Punkte durchgehen.
CHECKLIST_HEADERS = {
    "de": "Post-Upload-Checkliste (YouTube Studio)",
    "en": "Post-Upload Checklist (YouTube Studio)",
}


def build_post_upload_checklist(meta: dict, show_name: str) -> str:
    """Baut eine Markdown-Checkliste für manuelle YouTube-Studio-Schritte
    nach dem Upload. Infokarten-Vorschläge aus den Kapitel-Übergängen.
    """
    lang = meta.get("language", "de")
    is_de = lang == "de"
    header = CHECKLIST_HEADERS.get(lang, CHECKLIST_HEADERS["en"])

    chapters = meta.get("chapters", [])
    # Infokarten an thematischen Übergängen — max. 3 Vorschläge (1 pro starkem
    # Kapitel-Übergang, ohne Intro 00:00).
    card_chapters = [c for c in chapters if c.get("time") != "00:00"][:3]

    lines = [f'## {header}', '']
    if is_de:
        lines += [
            f'- [ ] **Playlist:** Video zur Playlist „{show_name}" hinzufügen (falls nicht durch Auto-Assignment erfolgt)',
            '- [ ] **Endscreen aktivieren** — Subscribe-Element + Next-Episode-Empfehlung aus Playlist (Visualizer ist in den letzten 20s endscreen-safe gerendert)',
            '- [ ] **Infokarten** an thematischen Übergängen platzieren:',
        ]
        if card_chapters:
            for ch in card_chapters:
                lines.append(f'      - [ ] `{ch["time"]}` — {ch["title"]}')
        else:
            lines.append('      - [ ] keine Kapitel-Übergänge erkannt — manuell entscheiden')
        lines += [
            '- [ ] **Auto-Kapitel** im Video-Detailbereich aktivieren (falls nicht via Kanal-Default)',
            '- [ ] **Community-Post** mit Teaser-Frage zum Inhalt veröffentlichen',
            '- [ ] **Thumbnail** prüfen: keine Gesichter/wichtigen Elemente im rechten unteren Bereich (Endscreen-Overlay-Zone)',
        ]
    else:
        lines += [
            f'- [ ] **Playlist:** Add video to „{show_name}" playlist (if not done by auto-assignment)',
            '- [ ] **Enable endscreen** — Subscribe element + next-episode recommendation from playlist (visualizer is endscreen-safe in the last 20s)',
            '- [ ] **Info cards** at thematic transitions:',
        ]
        if card_chapters:
            for ch in card_chapters:
                lines.append(f'      - [ ] `{ch["time"]}` — {ch["title"]}')
        else:
            lines.append('      - [ ] no chapter transitions detected — decide manually')
        lines += [
            '- [ ] **Auto-chapters** enabled in video details (unless set as channel default)',
            '- [ ] **Community post** with a teaser question about the content',
            '- [ ] **Thumbnail** check: no faces/important elements in lower-right (endscreen-overlay zone)',
        ]
    return '\n'.join(lines) + '\n'


def resolve_language(language: str, whisperx_path: str | None) -> str:
    """Löst 'auto' auf — liest erkannte Sprache aus WhisperX-JSON."""
    if language != "auto":
        return language
    if whisperx_path and os.path.exists(whisperx_path):
        with open(whisperx_path, encoding="utf-8") as f:
            data = json.load(f)
        detected = data.get("language", "")
        if detected:
            return detected
    return "de"


def generate_metadata(txt_path: str, whisperx_path: str | None = None,
                      show_name: str = "Signal", episode: str = "EP 01",
                      output_dir: str = "./output",
                      language: str = "de") -> dict:
    with open(txt_path, encoding="utf-8") as f:
        transcript = f.read()

    max_chars = 60_000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n[... Transkript gekürzt ...]"

    duration_min = estimate_duration(whisperx_path, txt_path)
    lang_code = resolve_language(language, whisperx_path)
    lang_name = LANGUAGE_NAMES.get(lang_code, lang_code.upper())

    print(f"Metadaten generieren via MLX ({MLX_MODEL.split('/')[-1]}, Sprache: {lang_name})...")
    raw = mlx_chat(
        system=SYSTEM_PROMPT.format(language_name=lang_name),
        user=GENERATION_PROMPT.format(
            transcript=transcript,
            show_name=show_name,
            episode=episode,
            duration_min=duration_min,
            language_name=lang_name,
            language_code=lang_code,
        ),
        temperature=0.2,  # niedrigere temp → sachlicher
        max_tokens=1200,  # 60-120 Wörter description + chapters + tags passt locker
    )

    try:
        meta = parse_json_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"FEHLER beim JSON-Parsing: {e}")
        sys.exit(1)

    if whisperx_path and (not meta.get("chapters") or len(meta["chapters"]) <= 1):
        meta["chapters"] = build_chapters_from_whisperx(whisperx_path)

    meta["description"] = format_description_with_chapters(meta)

    stem = Path(txt_path).stem
    os.makedirs(output_dir, exist_ok=True)

    json_out = os.path.join(output_dir, f"{stem}.youtube-meta.json")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  → {json_out}")

    md_out = os.path.join(output_dir, f"{stem}.youtube-meta.md")
    checklist = build_post_upload_checklist(meta, meta.get("show_name", show_name))
    with open(md_out, "w", encoding="utf-8") as f:
        f.write(f"""---
title: "{meta['title']}"
show_name: "{meta.get('show_name', show_name)}"
episode: "{episode}"
youtube_status: privat
tags:
{chr(10).join(f'  - "{t}"' for t in meta.get('tags', []))}
language: "{meta.get('language', 'de')}"
category_id: "{meta.get('category_id', '27')}"
---

# {meta['title']}

## Beschreibung

{meta['description']}

{checklist}
## Rohdaten

```json
{json.dumps(meta, ensure_ascii=False, indent=2)}
```
""")
    print(f"  → {md_out}")

    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube-Metadaten generieren (via MLX)")
    parser.add_argument("transcript", help="Transkript-Textdatei (.txt)")
    parser.add_argument("--whisperx", help="WhisperX-JSON für Zeitstempel")
    parser.add_argument("--show-name", default="Signal")
    parser.add_argument("--episode", default="EP 01")
    parser.add_argument("--language", "-l", default="de",
                        help="Sprache der Metadaten: de, en, auto, ... (Standard: de)")
    parser.add_argument("--output-dir", "-o", default="./output")
    parser.add_argument("--model", default=None,
                        help="MLX-Modell-ID (überschreibt MLX_MODEL env)")
    args = parser.parse_args()

    if args.model:
        os.environ["MLX_MODEL"] = args.model
        MLX_MODEL = args.model

    meta = generate_metadata(
        txt_path=args.transcript,
        whisperx_path=args.whisperx,
        show_name=args.show_name,
        episode=args.episode,
        output_dir=args.output_dir,
        language=args.language,
    )
    print(f"\n✓ Titel: {meta['title']}")
    print(f"  Tags: {', '.join(meta.get('tags', []))}")
    print(f"  Kapitel: {len(meta.get('chapters', []))}")
