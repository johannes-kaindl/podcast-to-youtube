#!/usr/bin/env python3
"""Regenerate the WebGUI screenshots in docs/images/.

End-to-end and self-contained: builds a synthetic demo output/ tree, starts the
real FastAPI/HTMX WebGUI, drives it into four states with Playwright (system
Chrome, dark theme forced), optimises the PNGs with pngquant, and cleans up.

    python tools/screenshots/regenerate.py            # default port 8799
    python tools/screenshots/regenerate.py --port 9000 --keep-demo

Prerequisites (see tools/screenshots/README.md):
  * a Python env that can run webgui.py, plus `pip install playwright`
  * Google Chrome installed (Playwright uses it via channel="chrome")
  * ffmpeg (poster frame) and, optionally, pngquant (PNG optimisation)
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

import demo_data  # same directory (sys.path[0])

REPO = Path(__file__).resolve().parents[2]
DOCS_IMAGES = REPO / "docs" / "images"

DIV = "─" * 60
TRANSCRIBE = [DIV, "SCHRITT 1: Transkription", DIV,
              "[1/4] Modell laden (large-v3-turbo, de)", "[2/4] Transkribieren",
              "[3/4] Wort-Alignment", "[4/4] Speaker-Diarization",
              "✓ Transkription fertig"]
META = [DIV, "SCHRITT 2: YouTube-Metadaten generieren", DIV,
        "Metadaten generieren via MLX (qwen2.5-7b-instruct-4bit) …",
        "✓ Metadaten geschrieben"]
RENDER_RUNNING = [DIV, "SCHRITT 3: Video rendern (Remotion)", DIV,
                  "Rendering 12.0%", "Rendering 24.0%", "Rendering 41.7%",
                  "Rendering 53.4%"]


def _render_done(stem: str) -> list[str]:
    return [DIV, "SCHRITT 3: Video rendern (Remotion)", DIV,
            "Rendering 12.0%", "Rendering 24.0%", "Rendering 53.4%",
            "Rendering 87.2%", "Rendering 100.0%",
            f"✓ Render fertig: output/{stem}/{stem}-dialogue.mp4"]


def _upload(url: str) -> list[str]:
    return [DIV, "SCHRITT 4: YouTube-Upload", DIV,
            "Upload zu YouTube als private …", f"✓ Hochgeladen: {url}"]


_URL = "https://youtu.be/qC7w-2hL"

# (output name, path, seeded log, progress bar)
TARGETS = [
    ("webgui-start", "/", None, None),
    ("webgui-running", "/runs/folge-082",
     TRANSCRIBE + META + RENDER_RUNNING,
     {"pct": 53, "left": "Rendering", "right": "53%"}),
    ("webgui-upload", "/runs/folge-083",
     TRANSCRIBE + META + _render_done("folge-083"),
     {"pct": 100, "left": "Render complete", "right": "100%"}),
    ("webgui-done", "/runs/folge-081",
     TRANSCRIBE + META + _render_done("folge-081") + _upload(_URL),
     {"pct": 100, "left": "Pipeline complete", "right": "4 / 4"}),
]

SEED_JS = """
([log, progress]) => {
  const el = document.getElementById('log');
  if (el && log && log.length) {
    el.innerHTML = '';
    for (const t of log) {
      const row = document.createElement('div'); row.className = 'row';
      const m = document.createElement('span'); m.className = 'mark'; m.textContent = '·';
      const s = document.createElement('span'); s.className = 'msg'; s.textContent = t;
      row.append(m, s); el.append(row);
    }
    el.scrollTop = el.scrollHeight;
  }
  if (progress) {
    const fill = document.querySelector('#progress .progress-fill');
    if (fill) fill.style.setProperty('--progress', progress.pct + '%');
    const metas = document.querySelectorAll('#progress .progress-meta span');
    if (metas[0]) metas[0].textContent = progress.left;
    if (metas[1]) metas[1].textContent = progress.right;
  }
  document.querySelectorAll('video').forEach(v => {
    try { v.pause(); v.currentTime = 0.1; } catch (e) {}
  });
}
"""


def _wait_healthz(base: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"WebGUI did not come up at {base} within {timeout}s")


def _capture(base: str, raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  device_scale_factor=2, color_scheme="dark")
        ctx.add_init_script("try{localStorage.setItem('theme','dark')}catch(e){}")
        page = ctx.new_page()
        for name, path, log, progress in TARGETS:
            page.goto(base + path, wait_until="networkidle")
            if log or progress:
                page.evaluate(SEED_JS, [log, progress])
            page.wait_for_timeout(700)  # let the video poster frame paint
            page.screenshot(path=str(raw_dir / f"{name}.png"), full_page=True)
            print(f"  captured {name}.png")
        browser.close()


def _optimise(raw_dir: Path) -> None:
    DOCS_IMAGES.mkdir(parents=True, exist_ok=True)
    has_pngquant = shutil.which("pngquant") is not None
    if not has_pngquant:
        print("  pngquant not found — copying raw PNGs (larger files)")
    for name, *_ in TARGETS:
        src = raw_dir / f"{name}.png"
        dst = DOCS_IMAGES / f"{name}.png"
        if has_pngquant:
            subprocess.run(["pngquant", "--quality=62-90", "--strip", "--speed", "1",
                            "--force", "--output", str(dst), str(src)], check=True)
        else:
            shutil.copyfile(src, dst)
        print(f"  wrote {dst.relative_to(REPO)} ({dst.stat().st_size // 1024} KB)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate docs/images WebGUI screenshots")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--keep-demo", action="store_true",
                    help="keep the synthetic output/ demo runs instead of deleting them")
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    print("• building demo output/ tree …")
    stems = demo_data.build(REPO)

    print(f"• starting WebGUI on {base} …")
    server = subprocess.Popen(
        [sys.executable, str(REPO / "webgui.py"), "--no-open",
         "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw_dir = REPO / "output" / "_shots"
    try:
        _wait_healthz(base)
        print("• capturing screenshots …")
        _capture(base, raw_dir)
        print("• optimising PNGs → docs/images/ …")
        _optimise(raw_dir)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        if not args.keep_demo:
            shutil.rmtree(raw_dir, ignore_errors=True)
            for stem in stems:
                shutil.rmtree(REPO / "output" / stem, ignore_errors=True)
            out = REPO / "output"
            if out.exists() and not any(out.iterdir()):
                out.rmdir()
    print("✓ done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
