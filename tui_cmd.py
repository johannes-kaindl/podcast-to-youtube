"""Build pipeline command from gathered TUI state."""
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineConfig:
    audio: str
    viz: str
    language: str
    model: str
    diarize: str
    episode: str
    show_name: str
    skip_transcribe: bool
    skip_meta: bool
    skip_render: bool
    skip_upload: bool


def is_pyannote_cached() -> bool:
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return os.path.isdir(
        os.path.join(hf_home, "hub", "models--pyannote--speaker-diarization-3.1")
    )


def can_diarize() -> bool:
    return bool(os.environ.get("HF_TOKEN")) or is_pyannote_cached()


def resolve_audio_path(audio: str, fallback_dir: Path) -> Path:
    """Expand ~, make absolute. CWD wins; fallback_dir tried if CWD-relative fails."""
    p = Path(audio).expanduser()
    if p.is_absolute():
        return p
    cwd_resolved = (Path.cwd() / p).resolve()
    if cwd_resolved.exists():
        return cwd_resolved
    return (fallback_dir / p).resolve()


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
