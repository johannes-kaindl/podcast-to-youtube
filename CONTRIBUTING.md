# Contributing

`podcast-to-youtube` is a **personal tool** built for one specific Mac-Silicon-only podcast workflow. It is not actively soliciting contributions — but issues and PRs are welcome if you hit a sharp edge.

## Bug reports

Please include:

- macOS version + CPU (`uname -a`)
- The relevant run log from `output/<stem>/run-*.log`
- Steps to reproduce, including the source audio properties (`ffprobe`)

## Pull requests

1. Run the tests: `.venv/bin/python -m pytest tests/ -q`
2. New features should land with tests. The bar for "unit-tested" is low — see `tests/` for examples.
3. The design spec lives in [`docs/superpowers/specs/`](docs/superpowers/specs/). If your PR materially changes the surface, update the spec or call out the divergence in the PR description.
4. Commits follow conventional-commits-ish (`feat(scope): summary`, `fix(scope): …`, `docs(scope): …`).
5. Anthropic Claude was a heavy contributor to this codebase — commits with substantial AI input carry `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` in the trailer.

## Out of scope

- Windows / Linux support — the pipeline is intentionally Mac-Silicon-only.
- Cloud transcription / rendering — local-first by design.
- Multi-user or hosted deployment — single-user, localhost only.

If you want a feature beyond that, opening an issue to discuss first is much faster than a surprise PR.
