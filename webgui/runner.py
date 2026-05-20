"""Subprocess lifecycle + SSE event queue.

JobRegistry is in-memory, single-slot. Both pipeline runs and uploads
share this slot — only one subprocess can run at a time.
"""
import asyncio
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

JobKind = Literal["pipeline", "upload"]


@dataclass
class StreamEvent:
    """One SSE event to push to subscribers."""
    type: Literal["log", "phase", "progress", "done"]
    data: dict[str, Any]
    seq: int = 0


@dataclass
class ActiveJob:
    stem: str
    audio_path: Path
    output_dir: Path
    process: subprocess.Popen | None
    log_file: Path
    kind: JobKind
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    seq: int = 0
    queue: asyncio.Queue[StreamEvent] | None = None


class JobRegistry:
    """Single-slot job registry. Thread-safe."""

    def __init__(self) -> None:
        self._slot: ActiveJob | None = None
        self._lock = threading.Lock()

    @property
    def current(self) -> ActiveJob | None:
        return self._slot

    def try_claim(self, job: ActiveJob) -> bool:
        with self._lock:
            if self._slot is not None:
                return False
            self._slot = job
            return True

    def release(self, job: ActiveJob) -> None:
        with self._lock:
            if self._slot is job:
                self._slot = None


# Module-level singleton (FastAPI app gets it via import)
registry = JobRegistry()
