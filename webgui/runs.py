"""Run-Historie scanner — lists past runs from output/*/run-state.json."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

PhaseName = Literal["transcribe", "meta", "render", "upload"]
PhaseStatus = Literal["pending", "running", "done", "aborted", "skipped"]
PHASES: tuple[PhaseName, ...] = ("transcribe", "meta", "render", "upload")


@dataclass
class RunSummary:
    stem: str
    audio_path: str
    started_at: datetime
    updated_at: datetime
    show_name: str
    episode: str
    phases: dict[PhaseName, PhaseStatus]
    youtube_url: str | None
    video_path: str | None
    duration_s: int | None       # total pipeline duration, only if all phases done/skipped
    waveform_seed: int            # for procedural Run-Card thumbnail
    raw: dict = field(repr=False)


def list_runs(output_root: Path) -> list[RunSummary]:
    """Scan output_root/*/run-state.json. Returns runs sorted by updated_at desc.

    The run's `stem` is taken from the parent directory name — the directory is
    the canonical identifier on disk, independent of any stem stored inside JSON.
    """
    if not output_root.exists():
        return []
    out = []
    for state_file in output_root.glob("*/run-state.json"):
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        try:
            out.append(_summarize(data, stem=state_file.parent.name))
        except (KeyError, ValueError, TypeError):
            continue
    out.sort(key=lambda r: r.updated_at, reverse=True)
    return out


def _summarize(data: dict, stem: str) -> RunSummary:
    phases_raw = data["phases"]
    phases: dict[PhaseName, PhaseStatus] = {
        p: phases_raw.get(p, {}).get("status", "pending") for p in PHASES
    }
    upload = phases_raw.get("upload", {})
    youtube_url = upload.get("url")
    video_path = phases_raw.get("render", {}).get("output")

    duration_s = None
    if all(phases[p] in ("done", "skipped") for p in PHASES):
        try:
            started = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            ended_str = phases_raw.get("upload", {}).get("finished_at") \
                     or phases_raw.get("render", {}).get("finished_at") \
                     or data["updated_at"]
            ended = datetime.fromisoformat(ended_str.replace("Z", "+00:00"))
            duration_s = int((ended - started).total_seconds())
        except (KeyError, ValueError):
            duration_s = None

    cfg = data.get("config", {})
    return RunSummary(
        stem=stem,
        audio_path=data.get("audio", ""),
        started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
        show_name=cfg.get("show_name", ""),
        episode=cfg.get("episode", ""),
        phases=phases,
        youtube_url=youtube_url,
        video_path=video_path,
        duration_s=duration_s,
        waveform_seed=int(hashlib.md5(stem.encode()).hexdigest()[:8], 16),
        raw=data,
    )


def filter_runs(runs: list[RunSummary], filt: str) -> list[RunSummary]:
    """Apply UI filter chip to a list of RunSummary."""
    if filt in ("all", ""):
        return runs
    if filt == "done":
        return [r for r in runs if all(r.phases[p] in ("done", "skipped") for p in PHASES)
                and r.phases["upload"] == "done"]
    if filt == "aborted":
        return [r for r in runs if any(r.phases[p] == "aborted" for p in PHASES)]
    if filt == "unfinished":
        return [r for r in runs if any(r.phases[p] in ("pending", "running") for p in PHASES)
                and not any(r.phases[p] == "aborted" for p in PHASES)]
    if filt == "not-uploaded":
        return [r for r in runs if r.phases["upload"] != "done"]
    return runs
