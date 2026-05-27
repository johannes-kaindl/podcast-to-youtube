---
name: Bug Report
about: Something is broken or behaving unexpectedly
labels: bug
---

## What happened?

<!-- Describe the unexpected behavior. Include the exact error message or log output. -->

## What did you expect?

<!-- What should have happened instead? -->

## Pipeline phase

<!-- Which phase failed? Check the WebGUI phase indicator or `output/<stem>/run-state.json`. -->
- [ ] Transcribe (WhisperX)
- [ ] Metadata (local MLX LLM)
- [ ] Render (Remotion)
- [ ] Upload (YouTube Data API)
- [ ] WebGUI / SSE stream
- [ ] TUI fallback
- [ ] Setup / OAuth / model download
- [ ] Other / unknown

## Reproduction steps

```bash
# Paste the exact command(s) you ran
```

## Logs

```
# Paste relevant lines from output/<stem>/run-*.log and/or the WebGUI live-log panel
```

## Environment

- macOS version:
- Apple Silicon chip (e.g. M2, M3, M4, M5):
- RAM:
- Repo commit / tag (`git rev-parse --short HEAD`):
- Python version (`python3 --version`):
- ffmpeg version (`ffmpeg -version | head -1`):
- MLX server running on port 8080? (`launchctl list ai.mlx.mlx-lm-server`):
- Source audio properties (`ffprobe -hide_banner <file>`):

## Additional context

<!-- Any other details — visualiser choice (dialogue/monologue), diarization on/off, custom prompts, network conditions, etc. -->
