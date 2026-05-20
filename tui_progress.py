"""Backwards-compatibility shim — re-exports from pipeline_core."""
from pipeline_core import ProgressEvent, match_line

__all__ = ["ProgressEvent", "match_line"]
