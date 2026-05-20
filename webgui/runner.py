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


def spawn_pipeline(
    cmd: list[str],
    stem: str,
    audio_path: Path,
    output_dir: Path,
    log_file: Path,
    registry: JobRegistry,
    kind: JobKind = "pipeline",
) -> ActiveJob:
    """Spawn a pipeline subprocess. Returns the ActiveJob.

    Raises RuntimeError if the registry slot is already taken.
    A background daemon thread reads stdout and writes each line to log_file.
    Once the subprocess exits, the registry is released.
    """
    job = ActiveJob(
        stem=stem, audio_path=audio_path, output_dir=output_dir,
        process=None, log_file=log_file, kind=kind,
    )
    if not registry.try_claim(job):
        raise RuntimeError(f"Slot is busy with {registry.current.stem!r}")

    output_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    job.process = proc

    def _reader():
        try:
            with log_file.open("w", encoding="utf-8", buffering=1) as f:
                f.write(f"# Pipeline-Run started {datetime.now().isoformat()}\n")
                f.write(f"# Command: {' '.join(cmd)}\n")
                f.write("# " + ("─" * 60) + "\n\n")
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    f.write(line + "\n")
            proc.wait()
        finally:
            registry.release(job)

    threading.Thread(target=_reader, daemon=True, name=f"run-{stem}").start()
    return job


def _classify_level(line: str) -> str:
    """Trivial log-level inference for styling (used by T8+ SSE events)."""
    low = line.lower()
    if "✓" in line or "fertig" in low or "complete" in low:
        return "success"
    if "✗" in line or "fehler" in low or "error" in low or "traceback" in low:
        return "error"
    if "warn" in low or "slow" in low:
        return "warn"
    if line.startswith("─") or line.startswith("SCHRITT") or low.startswith("phase"):
        return "phase"
    return "info"


# Module-level singleton (FastAPI app gets it via import)
registry = JobRegistry()
