#!/usr/bin/env python3
"""Synthetic, schema-accurate demo runs for the README screenshots.

Writes an ``output/<stem>/`` tree (run-state.json + transcript + YouTube
metadata) for three pipeline states, plus an on-brand poster MP4 for the
render-done states so the WebGUI ``<video>`` preview shows a credible first
frame. The data is fake but matches what the real pipeline writes, so the
shipped FastAPI/HTMX UI renders its populated states without a real run.

Importable: ``build(repo_root)`` does everything and returns the demo stems.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOW = "Notizen aus der Kammer"

# Poster frame (Kuro Signal / Spectre violet) rendered via Playwright, then
# looped into a short MP4 — the local Homebrew ffmpeg lacks the drawtext filter.
POSTER_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{{margin:0;width:1920px;height:1080px;overflow:hidden}}
 .stage{{width:1920px;height:1080px;position:relative;
   background:
     radial-gradient(1200px 720px at 50% 30%, rgba(168,120,255,.16), transparent 60%),
     linear-gradient(180deg,#16111f 0%,#0b0b12 55%,#07070b 100%);
   font-family:-apple-system,Helvetica,Arial,sans-serif;
   display:flex;flex-direction:column;align-items:center;justify-content:center}}
 .show{{color:#a878ff;font-weight:700;font-size:30px;letter-spacing:.42em;
   text-transform:uppercase;opacity:.92;margin:0 0 30px}}
 .title{{color:#f4f2f8;font-weight:700;font-size:78px;letter-spacing:-.01em;
   text-align:center;max-width:1500px;margin:0;line-height:1.06}}
 .rule{{width:220px;height:3px;background:#a878ff;opacity:.85;margin:42px 0 26px;
   box-shadow:0 0 24px rgba(168,120,255,.6)}}
 .ep{{color:#8a8694;font-size:28px;letter-spacing:.06em;margin:0}}
 .bars{{position:absolute;left:0;right:0;bottom:140px;display:flex;gap:10px;
   justify-content:center;align-items:flex-end;height:96px;opacity:.55}}
 .bars i{{width:8px;border-radius:3px;
   background:linear-gradient(180deg,#a878ff,rgba(168,120,255,.22))}}
</style></head><body><div class="stage">
 <p class="show">{show}</p><h1 class="title">{title}</h1>
 <div class="rule"></div><p class="ep">{ep}</p>
 <div class="bars">{bars}</div>
</div></body></html>"""

# ---- transcripts (speaker: text, max 8 lines shown by the WebGUI) -------------
TRANSCRIPTS = {
    "folge-081": [
        "Anna: Willkommen zu Folge 81 von Notizen aus der Kammer.",
        "Ben: Heute mit einer steilen These: Aufmerksamkeit ist keine Ressource.",
        "Anna: Das musst du erklären – alle reden doch von der Aufmerksamkeitsökonomie.",
        "Ben: Genau das ist das Problem. Wir behandeln sie wie Öl im Tank.",
        "Anna: Also als etwas, das sich aufbraucht und nachgefüllt werden muss.",
        "Ben: Aber Aufmerksamkeit verhält sich eher wie ein Muskel.",
        "Anna: Sie ermüdet, klar – aber durch Gebrauch wird sie auch stärker.",
        "Ben: Und genau da setzt unsere heutige Folge an.",
    ],
    "folge-082": [
        "Anna: In dieser Folge geht es um die Pausen, die wir überhören.",
        "Ben: Die Stille zwischen zwei Gedanken – klingt esoterisch, ist es aber nicht.",
        "Anna: Nein, es gibt handfeste Forschung dazu.",
        "Ben: Das sogenannte Default Mode Network wird genau dann aktiv.",
        "Anna: Also immer dann, wenn wir scheinbar gar nichts tun.",
        "Ben: Und trotzdem arbeitet das Gehirn auf Hochtouren weiter.",
    ],
    "folge-083": [
        "Anna: Folge 83 – Werkzeuge, die uns benutzen.",
        "Ben: Eine Umkehrung der üblichen Erzählung.",
        "Anna: Normalerweise heißt es: der Mensch nutzt das Werkzeug.",
        "Ben: Aber jedes Werkzeug formt auch den, der es führt.",
        "Anna: McLuhan lässt grüßen.",
        "Ben: Wir schauen uns heute drei konkrete Beispiele an.",
    ],
}

# ---- YouTube metadata ---------------------------------------------------------
META = {
    "folge-081": {
        "title": "Warum Aufmerksamkeit keine Ressource ist",
        "description": (
            "Alle reden von der Aufmerksamkeitsökonomie – als wäre Aufmerksamkeit "
            "ein endlicher Vorrat, der sich aufbraucht. In Folge 81 drehen wir die "
            "Metapher um: Aufmerksamkeit verhält sich weniger wie Öl im Tank und "
            "mehr wie ein Muskel, der durch Training wächst. Wir sprechen über das "
            "Default Mode Network, über Deep Work und darüber, was „Fokus trainieren“ "
            "konkret bedeutet."
        ),
        "tags": ["Aufmerksamkeit", "Achtsamkeit", "Fokus", "Produktivität",
                 "Neurowissenschaft", "Default Mode Network", "Konzentration",
                 "Deep Work", "Podcast", "Notizen aus der Kammer", "Kognition",
                 "Aufmerksamkeitsökonomie", "Mentale Gesundheit"],
        "chapters": [
            {"time": "00:00", "title": "Kaltstart: die These"},
            {"time": "03:12", "title": "Aufmerksamkeitsökonomie, kurz erklärt"},
            {"time": "08:40", "title": "Der Muskel-Vergleich"},
            {"time": "15:05", "title": "Was Training konkret heißt"},
            {"time": "22:18", "title": "Fazit und Ausblick"},
        ],
    },
    "folge-082": {
        "title": "Die Stille zwischen zwei Gedanken",
        "description": (
            "Wir übersehen ständig die Pausen – die Sekunden, in denen scheinbar "
            "nichts passiert. Dabei wird genau dann das Default Mode Network aktiv. "
            "Diese Folge ist eine kleine Verteidigung der Leerstellen."
        ),
        "tags": ["Stille", "Default Mode Network", "Gehirn", "Achtsamkeit",
                 "Kreativität", "Neurowissenschaft", "Pausen", "Fokus",
                 "Podcast", "Notizen aus der Kammer", "Meditation"],
        "chapters": [
            {"time": "00:00", "title": "Was wir überhören"},
            {"time": "04:30", "title": "Das Default Mode Network"},
            {"time": "11:55", "title": "Stille als Werkzeug"},
            {"time": "18:20", "title": "Praxis für den Alltag"},
        ],
    },
    "folge-083": {
        "title": "Werkzeuge, die uns benutzen",
        "description": (
            "Der Mensch nutzt das Werkzeug – so die übliche Erzählung. Aber jedes "
            "Werkzeug formt auch den, der es führt. Anhand von drei Beispielen drehen "
            "wir die Perspektive um und fragen, wer hier eigentlich wen benutzt."
        ),
        "tags": ["Werkzeuge", "Technologie", "McLuhan", "Medientheorie",
                 "Philosophie", "Kulturkritik", "Gewohnheiten", "Design",
                 "Podcast", "Notizen aus der Kammer", "Aufmerksamkeit"],
        "chapters": [
            {"time": "00:00", "title": "Die umgekehrte These"},
            {"time": "02:48", "title": "Beispiel 1: die Tastatur"},
            {"time": "09:10", "title": "Beispiel 2: der Kalender"},
            {"time": "16:02", "title": "Beispiel 3: das Smartphone"},
            {"time": "23:40", "title": "Was bleibt"},
        ],
    },
}

# ---- run-state.json per state (drives the WebGUI variant) ---------------------
RUN_STATES = {
    # Live run: transcribe+meta done, render in progress, upload pending.
    "folge-082": {
        "schema_version": 1, "audio": "/Users/jay/Audio/folge-082.m4a",
        "stem": "folge-082", "started_at": "2026-05-20T14:02:11Z",
        "updated_at": "2026-05-20T14:09:53Z",
        "config": {"show_name": SHOW, "episode": "Folge 82", "language": "de",
                   "model": "large-v3-turbo", "viz_type": "dialogue",
                   "diarize": True, "num_speakers": None},
        "phases": {
            "transcribe": {"status": "done", "finished_at": "2026-05-20T14:05:25Z"},
            "meta": {"status": "done", "title": META["folge-082"]["title"],
                     "finished_at": "2026-05-20T14:06:08Z"},
            "render": {"status": "running", "started_at": "2026-05-20T14:06:08Z"},
            "upload": {"status": "pending"},
        },
    },
    # Trust moment: render done, awaiting an explicit upload decision.
    "folge-083": {
        "schema_version": 1, "audio": "/Users/jay/Audio/folge-083.m4a",
        "stem": "folge-083", "started_at": "2026-05-26T19:40:00Z",
        "updated_at": "2026-05-26T20:03:42Z",
        "config": {"show_name": SHOW, "episode": "Folge 83", "language": "de",
                   "model": "large-v3-turbo", "viz_type": "dialogue",
                   "diarize": True, "num_speakers": None, "privacy": "private"},
        "phases": {
            "transcribe": {"status": "done", "finished_at": "2026-05-26T19:43:18Z"},
            "meta": {"status": "done", "title": META["folge-083"]["title"],
                     "finished_at": "2026-05-26T19:44:01Z"},
            "render": {"status": "done", "size_mb": 176.0,
                       "output": "folge-083-dialogue.mp4",
                       "finished_at": "2026-05-26T20:03:42Z"},
            "upload": {"status": "pending"},
        },
    },
    # Terminal success: all four phases done, uploaded to YouTube.
    "folge-081": {
        "schema_version": 1, "audio": "/Users/jay/Audio/folge-081.m4a",
        "stem": "folge-081", "started_at": "2026-05-18T09:14:00Z",
        "updated_at": "2026-05-18T09:36:18Z",
        "config": {"show_name": SHOW, "episode": "Folge 81", "language": "de",
                   "model": "large-v3-turbo", "viz_type": "dialogue",
                   "diarize": True, "num_speakers": None, "privacy": "private"},
        "phases": {
            "transcribe": {"status": "done", "started_at": "2026-05-18T09:14:00Z",
                           "finished_at": "2026-05-18T09:17:14Z"},
            "meta": {"status": "done", "started_at": "2026-05-18T09:17:14Z",
                     "finished_at": "2026-05-18T09:17:56Z",
                     "title": META["folge-081"]["title"]},
            "render": {"status": "done", "started_at": "2026-05-18T09:17:56Z",
                       "finished_at": "2026-05-18T09:30:11Z", "size_mb": 198.0,
                       "output": "folge-081-dialogue.mp4"},
            "upload": {"status": "done", "started_at": "2026-05-18T09:30:11Z",
                       "finished_at": "2026-05-18T09:36:18Z",
                       "url": "https://youtu.be/qC7w-2hL", "video_id": "qC7w-2hL"},
        },
    },
}

# stems that have a rendered video → need a poster MP4
VIDEO_STEMS = {"folge-081": "folge-081-dialogue.mp4",
               "folge-083": "folge-083-dialogue.mp4"}

# capture order: hero first, then the three rich states
STEMS = ["folge-082", "folge-083", "folge-081"]


def _wave_bars(stem: str, n: int = 56) -> str:
    """Deterministic, audio-shaped bar heights (no RNG → reproducible)."""
    seed = hashlib.md5(stem.encode()).digest()
    out = []
    for i in range(n):
        env = 0.45 + 0.55 * (1 - abs(i - n / 2) / (n / 2))
        h = int((16 + (seed[i % len(seed)] / 255) * 78) * env)
        out.append(f'<i style="height:{max(8, h)}px"></i>')
    return "".join(out)


def _make_poster(stem: str, mp4_name: str, out_dir: Path, page) -> None:
    html = POSTER_HTML.format(
        show=SHOW.upper(), title=META[stem]["title"],
        ep=RUN_STATES[stem]["config"]["episode"], bars=_wave_bars(stem))
    png = out_dir / "_poster.png"
    page.set_content(html, wait_until="networkidle")
    page.screenshot(path=str(png))
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png),
        "-t", "2", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080", "-movflags", "+faststart",
        str(out_dir / mp4_name),
    ], check=True)
    png.unlink()


def build(repo_root: Path) -> list[str]:
    """Write the demo output/ tree and poster MP4s. Returns the demo stems."""
    out = repo_root / "output"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080},
                                device_scale_factor=1)
        for stem, state in RUN_STATES.items():
            d = out / stem
            d.mkdir(parents=True, exist_ok=True)
            (d / "run-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
            (d / f"{stem}.txt").write_text("\n".join(TRANSCRIPTS[stem]) + "\n", encoding="utf-8")
            (d / f"{stem}.youtube-meta.json").write_text(
                json.dumps(META[stem], indent=2, ensure_ascii=False), encoding="utf-8")
            if stem in VIDEO_STEMS:
                _make_poster(stem, VIDEO_STEMS[stem], d, page)
        browser.close()
    return list(RUN_STATES)
