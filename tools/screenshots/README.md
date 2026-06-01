# WebGUI screenshot regeneration

Regenerates the WebGUI screenshots in [`docs/images/`](../../docs/images/) used by
the top-level `README.md`.

The screenshots are of the **real** shipped FastAPI/HTMX WebGUI — not mockups. The
tool fakes only the *data*: it writes a synthetic `output/<stem>/` tree (schema-accurate
`run-state.json` + transcript + YouTube metadata, plus a poster MP4) for three pipeline
states, starts `webgui.py`, and drives the live UI into each state with Playwright.

## What it produces

| File | State | Source |
|---|---|---|
| `webgui-start.png` | Start / configuration screen (the README hero) | `/` |
| `webgui-running.png` | Live run — render in progress, log streaming | `folge-082` |
| `webgui-upload.png` | Trust moment — render done, upload card | `folge-083` |
| `webgui-done.png` | Finished — all phases done, uploaded | `folge-081` |

Dark theme is forced. The log panel is seeded with the project's real captured pipeline
stdout (mirroring `tests/fixtures/stdout-snippets/`) so it looks like a live run.

## Prerequisites

- A Python environment that can run `webgui.py` (the project's web deps:
  `fastapi`, `uvicorn[standard]`, `jinja2`, `sse-starlette`, `python-multipart`,
  `python-dotenv`) **plus** `playwright`:
  ```bash
  uv venv .venv --python 3.12 && source .venv/bin/activate
  uv pip install fastapi "uvicorn[standard]" jinja2 sse-starlette python-multipart python-dotenv playwright
  ```
  (Installing the full `requirements.txt` works too — it just also pulls the heavy
  ML stack, which the screenshots don't need.)
- **Google Chrome** installed — Playwright uses it via `channel="chrome"`, so no
  browser download is required.
- **ffmpeg** (for the poster frame) and, optionally, **pngquant** (PNG optimisation;
  without it the raw, larger PNGs are copied through).

> Note: the local Homebrew ffmpeg is built without `libfreetype`, so the poster text is
> rendered as HTML via Playwright and looped into an MP4 — `drawtext` is not used.

## Run

```bash
python tools/screenshots/regenerate.py            # default port 8799
python tools/screenshots/regenerate.py --port 9000 --keep-demo
```

It builds the demo data, captures, optimises into `docs/images/`, then stops the
server and deletes the synthetic `output/` runs (`--keep-demo` keeps them for
inspection). The capture is deterministic, so re-running produces the same images.

## Files

- `regenerate.py` — orchestrator (build → serve → capture → optimise → clean up)
- `demo_data.py` — the synthetic run-states, transcripts, metadata and poster builder
