# Contributing

`podcast-to-youtube` is a **personal tool** built for one specific Mac-Silicon-only podcast workflow. It is not actively soliciting contributions — but issues and PRs are welcome if you hit a sharp edge.

## Bug reports & feature requests

Use the [Codeberg issue tracker](https://codeberg.org/jkaindl/podcast-to-youtube/issues) — the [bug-report and feature-request templates](.forgejo/issue_template/) prompt for everything below.

For bug reports please include:

- macOS version + CPU (`uname -a`)
- Repo commit / tag (`git rev-parse --short HEAD`)
- The relevant run log from `output/<stem>/run-*.log`
- Steps to reproduce, including the source audio properties (`ffprobe`)

For security-sensitive reports see [`SECURITY.md`](SECURITY.md) — please **do not** file a public issue.

## Development setup

```bash
git clone https://codeberg.org/jkaindl/podcast-to-youtube.git
cd podcast-to-youtube

uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

brew install ffmpeg
cd visualizer && npm install && cd ..
```

## Pull requests

1. **Tests first.** TDD with a failing test, then the implementation. New features land with tests. The bar for "unit-tested" is intentionally low — match what's in `tests/`.
2. **Run the local suite before pushing:**
   ```bash
   .venv/bin/python -m pytest tests/ -q       # 64 unit + integration tests, ~3 s
   ```
3. **HTTP / SSE code needs real request tests.** WebGUI route changes must be covered with `starlette.testclient.TestClient` requests, not just mocked units — past SSE-reconnect bugs slipped through mock-only coverage.
4. **Atomic slices.** Implement in small, self-contained slices; commit per slice; bundle into a release when a set of slices is complete. The design spec lives in [`docs/superpowers/specs/`](docs/superpowers/specs/) — if your PR materially changes the surface, update the spec or call out the divergence in the PR description.
5. **Conventional commits** — `feat(scope): summary`, `fix(scope): …`, `docs(scope): …`, `chore(scope): …`, `refactor(scope): …`.
6. **AI co-author trailer.** Anthropic Claude was a heavy contributor to this codebase. Commits with substantial AI input use:
   ```
   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```

## Out of scope

- Windows / Linux support — the pipeline is intentionally Mac-Silicon-only.
- Cloud transcription / rendering — local-first by design.
- Multi-user or hosted deployment — single-user, localhost only.
- Public binding of the WebGUI — it binds to `127.0.0.1` by design; no `--host 0.0.0.0` flag is planned.

If you want a feature beyond that, opening an issue to discuss first is much faster than a surprise PR.
