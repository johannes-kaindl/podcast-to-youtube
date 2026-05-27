# Security Policy

## Scope

`podcast-to-youtube` is a **local-first, single-user Mac tool**. It does not ship a hosted service. The attack surface is:

- The local CLI (`python pipeline.py`, `python upload_youtube.py`, …)
- The WebGUI served at `http://127.0.0.1:8765` (`python webgui.py`)
- The OAuth flow against the YouTube Data API v3 (`python auth_youtube.py`)
- The transcript/metadata calls against the local MLX server at `http://localhost:8080`
- The pickle-cached OAuth token at `.youtube_token.pickle` and the Google client secrets at `client_secrets.json` (both gitignored, never committed)

The pipeline shells out to `ffmpeg` / `ffprobe`, the WhisperX model code, the MLX runtime and Remotion (Node) and assumes those binaries are trusted local installs.

The WebGUI binds to `127.0.0.1` only — there is no `--host 0.0.0.0` flag. Remote / LAN exposure is **not** a supported configuration.

## Supported versions

Only the latest minor release (currently `v1.0.x`) receives fixes. Older releases are kept as historical references.

## Reporting a vulnerability

**Please do not file a public issue for security-sensitive reports.**

Preferred channel:

- Email: **code.jkaindl@mailbox.org**
- Subject line: `[security] podcast-to-youtube: <short description>`

If you don't get an acknowledgement within 7 days, please open a placeholder Codeberg issue titled `Security report pending` (no details) and mention that you tried email — that flags it without disclosing the vulnerability.

Please include:

- The affected version (`git rev-parse --short HEAD` or release tag)
- A minimal reproduction (source audio properties via `ffprobe`, CLI invocation or HTTP request, expected vs. observed behaviour)
- Any relevant lines from `output/<stem>/run-*.log`
- macOS version + CPU (`uname -a`)
- Your suggested severity / impact assessment

## Disclosure

This is a solo-maintained project. Realistic timeline:

- **Acknowledgement:** within 7 days
- **Triage + fix or mitigation:** best-effort within 30 days for high-severity issues
- **Public disclosure:** after a fix is released, with credit to the reporter unless they request anonymity

## Out of scope

- Issues that require pre-existing local code execution as the user (the pipeline already runs as the user and trusts the user's environment)
- Issues that require deliberately exposing the WebGUI on a public interface (it binds to `127.0.0.1` by design)
- Dependency-chain CVEs that don't affect the pipeline's actual code paths — please report those upstream first
- Issues with the YouTube Data API itself (report to Google) or with Apple's CoreML / MLX stack (report to Apple)

Thanks for taking the time to report responsibly.
