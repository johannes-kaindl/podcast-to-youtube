"""Audio-probe + pre-flight helpers (ffprobe, disk-free, ETA-heuristic)."""
import json
import shutil
import subprocess
from pathlib import Path

SUPPORTED_EXTS = {".m4a", ".mp3", ".wav"}

# ETA factors per phase (× audio-duration-seconds, on M-series Mac)
_MODEL_FACTORS = {
    "large-v3-turbo": 0.045,
    "large-v3":       0.18,
    "large-v2":       0.16,
    "medium":         0.08,
    "small":          0.04,
    "base":           0.02,
    "tiny":           0.01,
}
_VIZ_FACTORS = {"dialogue": 0.17, "monologue": 0.15}
_META_FIXED_S = 45
_UPLOAD_FACTOR = 0.03    # bandwidth-dependent — heuristic only


def audio_probe(audio_path: Path, output_root: Path) -> dict:
    """Probe audio file. Returns dict with 'valid' bool + audio/resume metadata."""
    if not audio_path.exists():
        return {"valid": False, "error": "file_not_found"}
    if audio_path.suffix.lower() not in SUPPORTED_EXTS:
        return {"valid": False, "error": "format_unsupported"}

    try:
        ff = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams",
             "-of", "json", str(audio_path)],
            capture_output=True, text=True, check=True, timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {"valid": False, "error": "ffprobe_failed"}

    probe = json.loads(ff.stdout)
    fmt = probe.get("format", {})
    audio_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "audio"),
        {},
    )

    stem = audio_path.stem
    output_dir = output_root / stem
    state_file = output_dir / "run-state.json"
    resume_state = None
    if state_file.exists():
        try:
            resume_state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            resume_state = None

    duration_s = float(fmt.get("duration", 0))

    disk_root = output_root if output_root.exists() else output_root.parent
    return {
        "valid": True,
        "stem": stem,
        "size_bytes": audio_path.stat().st_size,
        "duration_s": duration_s,
        "format": fmt.get("format_name", "unknown"),
        "channels": int(audio_stream.get("channels", 0)),
        "sample_rate": int(audio_stream.get("sample_rate", 0)),
        "resume_state": resume_state,
        "disk_free_bytes": shutil.disk_usage(disk_root).free,
        "eta_estimate_s": eta_estimate(duration_s, model="large-v3-turbo", viz="dialogue"),
    }


def eta_estimate(duration_s: float, model: str, viz: str) -> dict[str, float]:
    """Heuristic ETA per phase in seconds; M-series-Mac heuristic only."""
    transcribe = duration_s * _MODEL_FACTORS.get(model, 0.045)
    meta = float(_META_FIXED_S)
    render = duration_s * _VIZ_FACTORS.get(viz, 0.17)
    upload = duration_s * _UPLOAD_FACTOR
    return {
        "transcribe": transcribe,
        "meta": meta,
        "render": render,
        "upload": upload,
        "total": transcribe + meta + render + upload,
    }
