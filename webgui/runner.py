"""Subprocess lifecycle + SSE event queue.

JobRegistry is in-memory, single-slot. Both pipeline runs and uploads
share this slot — only one subprocess can run at a time.
"""
import asyncio
import shlex
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
    """Spawn a pipeline subprocess. Returns the ActiveJob (with attached asyncio.Queue).

    Raises RuntimeError if the registry slot is already taken.
    A background daemon thread reads stdout, writes each line to log_file, AND
    pushes a StreamEvent into job.queue (via loop.call_soon_threadsafe) so an
    SSE consumer can drain events on the main asyncio loop. Once the subprocess
    exits, the registry is released and a "done" event is emitted.
    """
    job = ActiveJob(
        stem=stem, audio_path=audio_path, output_dir=output_dir,
        process=None, log_file=log_file, kind=kind,
        queue=asyncio.Queue(),
    )
    if not registry.try_claim(job):
        # Capture the current slot owner outside the format-string so a
        # release-between-check-and-format race can't raise AttributeError.
        existing = registry.current
        existing_stem = existing.stem if existing is not None else "<unknown>"
        raise RuntimeError(f"Slot is busy with {existing_stem!r}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception:
        # Popen (or mkdir) failed BEFORE the slot-releasing reader-thread starts.
        # Without this, the registry singleton would be permanently stuck.
        registry.release(job)
        raise
    job.process = proc

    # Capture the running event loop so the reader thread can push to the queue.
    # If there's no loop (e.g. spawn_pipeline called from a sync context like a
    # bare unit test), fall back to None — queue events are silently dropped.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    def _put(event: StreamEvent) -> None:
        if loop is None or job.queue is None:
            return
        try:
            loop.call_soon_threadsafe(job.queue.put_nowait, event)
        except RuntimeError:
            # Loop already closed (e.g. test client teardown, server shutdown).
            # Reader thread continues writing to the log file regardless.
            pass

    def _reader():
        from pipeline_core import match_line
        current_step = 0
        try:
            with log_file.open("w", encoding="utf-8", buffering=1) as f:
                f.write(f"# Pipeline-Run started {job.started_at.isoformat()}\n")
                f.write(f"# Command: {shlex.join(cmd)}\n")
                f.write("# " + ("─" * 60) + "\n\n")
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    f.write(line + "\n")
                    if not line:
                        continue
                    job.seq += 1
                    _put(StreamEvent(
                        type="log",
                        seq=job.seq,
                        data={"msg": line, "level": _classify_level(line)},
                    ))
                    evt = match_line(line, current_step)
                    if evt is not None:
                        current_step = evt.step
                        job.seq += 1
                        _put(StreamEvent(
                            type="phase",
                            seq=job.seq,
                            data={"step": evt.step, "label": evt.label},
                        ))
                        job.seq += 1
                        _put(StreamEvent(
                            type="progress",
                            seq=job.seq,
                            data={"value": evt.progress, "label": evt.label},
                        ))
            if proc.stdout is not None:
                proc.stdout.close()
            proc.wait()
            job.seq += 1
            _put(StreamEvent(
                type="done",
                seq=job.seq,
                data={"exit_code": proc.returncode, "kind": kind},
            ))
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


def latest_logfile(output_dir: Path) -> Path | None:
    """Return the newest run-*.log in output_dir, or None if none exists."""
    if not output_dir.exists():
        return None
    logs = sorted(output_dir.glob("run-*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def replay_logfile(log_file: Path, start_seq: int = 0):
    """Yield StreamEvent log lines from a logfile, starting AFTER start_seq.

    Lines starting with '#' or blank lines are header/separator — skipped
    (not counted toward seq). Each real line gets a monotonically-increasing
    seq starting at 1.
    """
    if not log_file.exists():
        return
    seq = 0
    for raw_line in log_file.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        seq += 1
        if seq <= start_seq:
            continue
        yield StreamEvent(
            type="log",
            seq=seq,
            data={"msg": raw_line, "level": _classify_level(raw_line)},
        )


# Module-level singleton (FastAPI app gets it via import)
registry = JobRegistry()
