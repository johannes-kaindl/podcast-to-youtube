"""Backwards-compatibility shim — re-exports from pipeline_core."""

from pipeline_core import (
    PipelineConfig,
    build_command,
    can_diarize,
    is_pyannote_cached,
    resolve_audio_path,
)

__all__ = [
    "PipelineConfig",
    "build_command",
    "can_diarize",
    "is_pyannote_cached",
    "resolve_audio_path",
]
