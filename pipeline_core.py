"""Shared helpers used by both the TUI and the WebGUI.

Pure-Python module with no UI dependencies (no textual, no fastapi).
Owns the pipeline-config dataclass, command builder, audio-path resolution,
diarization-availability check, and the stdout-line classifier.
"""
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# ── Pipeline-config dataclass ─────────────────────────────────────────────
@dataclass
class PipelineConfig:
    audio: str
    viz: str
    language: str
    model: str
    diarize: str            # "auto" | "off" | "2" | "3" | ...
    episode: str
    show_name: str
    skip_transcribe: bool
    skip_meta: bool
    skip_render: bool
    skip_upload: bool


# ── Diarization availability ──────────────────────────────────────────────
def is_pyannote_cached() -> bool:
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return os.path.isdir(
        os.path.join(hf_home, "hub", "models--pyannote--speaker-diarization-3.1")
    )


def can_diarize() -> bool:
    return bool(os.environ.get("HF_TOKEN")) or is_pyannote_cached()


# ── Audio-path resolution ─────────────────────────────────────────────────
def resolve_audio_path(audio: str, fallback_dir: Path) -> Path:
    """Expand ~, make absolute. CWD wins; fallback_dir tried if CWD-relative fails."""
    p = Path(audio).expanduser()
    if p.is_absolute():
        return p
    cwd_resolved = (Path.cwd() / p).resolve()
    if cwd_resolved.exists():
        return cwd_resolved
    return (fallback_dir / p).resolve()


# ── Command builder ───────────────────────────────────────────────────────
def build_command(config: PipelineConfig, pipeline_dir: Path) -> list[str]:
    cmd = [
        sys.executable, str(pipeline_dir / "pipeline.py"), config.audio,
        "--viz", config.viz, "--language", config.language, "--model", config.model,
        "--episode", config.episode, "--show-name", config.show_name,
    ]
    if config.diarize == "off":
        cmd.append("--no-diarize")
    elif config.diarize.isdigit():
        cmd.extend(["--speakers", config.diarize])
    if config.skip_transcribe: cmd.append("--skip-transcribe")
    if config.skip_meta:       cmd.append("--skip-meta")
    if config.skip_render:     cmd.append("--skip-render")
    if config.skip_upload:     cmd.append("--skip-upload")
    return cmd


# ── Progress event dataclass ──────────────────────────────────────────────
@dataclass
class ProgressEvent:
    progress: float    # 0–100
    label: str         # display label
    step: int          # 1–4


# ── Stdout-line classifier ────────────────────────────────────────────────
_STEP_MARKERS = [
    (re.compile(r"SCHRITT 1:"),               1, "Schritt 1/4 · Transkription",          2),
    (re.compile(r"\[1/4\] Modell"),           1, "Schritt 1/4 · Modell laden …",         5),
    (re.compile(r"\[2/4\] Transkrib"),        1, "Schritt 1/4 · Transkribieren …",       15),
    (re.compile(r"\[3/4\] Wort"),             1, "Schritt 1/4 · Wort-Alignment …",       32),
    (re.compile(r"\[4/4\]"),                  1, "Schritt 1/4 · Speaker-Erkennung …",    39),
    (re.compile(r"SCHRITT 2:"),               2, "Schritt 2/4 · Metadaten generieren …", 44),
    (re.compile(r"Metadaten generieren via"), 2, "Schritt 2/4 · LLM generiert …",        47),
    (re.compile(r"SCHRITT 3:"),               3, "Schritt 3/4 · Video rendern …",        53),
    (re.compile(r"SCHRITT 4:"),               4, "Schritt 4/4 · YouTube-Upload …",       96),
]
_RENDER_PCT_RE = re.compile(r"Rendering\s+(\d+\.?\d*)%")


def match_line(line: str, current_step: int) -> ProgressEvent | None:
    """Map a single stdout line to a progress event, or None if it doesn't match."""
    for pattern, step, label, progress in _STEP_MARKERS:
        if pattern.search(line):
            return ProgressEvent(progress, label, step)
    if current_step == 3:
        m = _RENDER_PCT_RE.search(line)
        if m:
            pct = float(m.group(1))
            overall = 53.0 + pct * 42.0 / 100.0
            return ProgressEvent(overall, f"Schritt 3/4 · Rendering {pct:.0f}%", 3)
    return None
