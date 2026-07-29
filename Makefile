# Standard targets (PROF-PY-06). Everything runs through uv — no manual venv.
#
#   make install   # sync the env (add --extra transcribe for WhisperX)
#   make check     # the full gate: lint + typecheck + test (mirrors pre-push)
#   make serve     # run the WebGUI (the primary interface)

.PHONY: install build lint format typecheck test test-all check check-no-abs-paths serve watch screenshots hooks

install:
	uv sync

build: check  # flat app (package = false) → no wheel; "build" is the full quality gate

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy .

test:
	uv run pytest tests/ -q -m "not slow and not needs_models and not needs_youtube"

test-all:  # incl. slow + integration tests (need WhisperX models / YouTube creds)
	uv run pytest tests/ -q

check-no-abs-paths:  # CORE-META-14 gate: no absolute maintainer paths in tracked *.md
	node scripts/check-no-abs-paths.mjs

check: check-no-abs-paths lint typecheck test  # the full gate, as pre-push runs it

serve:  # the WebGUI on http://localhost:8765
	uv run python webgui.py

watch:  # WebGUI with autoreload on file change
	uv run python webgui.py --reload

screenshots:  # regenerate docs/images/ from the live WebGUI
	uv run python tools/screenshots/regenerate.py

hooks:  # install the git hooks
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push
