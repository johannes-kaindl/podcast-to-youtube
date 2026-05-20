"""Backwards-compatibility shim — re-exports from pipeline_core."""
from pipeline_core import (
    PipelineConfig,
    is_pyannote_cached,
    can_diarize,
    resolve_audio_path,
    build_command,
)

__all__ = [
    "PipelineConfig", "is_pyannote_cached", "can_diarize",
    "resolve_audio_path", "build_command",
]
