#!/usr/bin/env python3
"""
Remotion-Video aus Audio + WhisperX-JSON rendern.
Kopiert Dateien in public/, konvertiert zu MP3, ruft Remotion auf.

Usage:
  python render_video.py audio.m4a --whisperx audio.whisperx.json --srt audio.srt
  python render_video.py audio.m4a --whisperx audio.whisperx.json --viz ring --title "Mein Podcast"
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REMOTION_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../10_ObsidianVaults/00_ShadowVault/20-projekte/"
    "26-001 Whisper Audio-Transkription Pipeline/"
    "05-visuals/Remotion Rendering"
)
# Absoluter Pfad
REMOTION_DIR = os.path.realpath(os.path.join(
    "/Users/Shared/20_Claude/26-001-whisper-pipeline",
    "../../10_ObsidianVaults/00_ShadowVault/20-projekte/"
    "26-001 Whisper Audio-Transkription Pipeline/"
    "05-visuals/Remotion Rendering"
))


def render(audio_path: str, whisperx_path: str, srt_path: str | None = None,
           output_path: str | None = None, viz_type: str = "dialogue",
           title: str = "Podcast", episode: str = "EP 01",
           show_name: str = "Kuro Signal", duration_frames: int | None = None) -> str:

    public_dir = os.path.join(REMOTION_DIR, "public")
    os.makedirs(public_dir, exist_ok=True)

    # Audio zu WAV konvertieren (useWindowedAudioData braucht RIFF/WAV).
    # `apad=pad_dur=20` hängt 20s Silence ans Ende — die Compositions verwenden
    # useWindowedAudioData mit windowInSeconds=30 (±15s um den aktuellen Frame),
    # also würde das Window in den letzten 15s sonst über EOF lesen und der
    # Remotion-Dev-Server antwortet mit HTTP 416. Root.tsx zieht das Padding
    # via AUDIO_TRAILING_PAD_SECONDS wieder ab, sodass das Video exakt am
    # Original-Audio-Ende stoppt.
    AUDIO_PAD_SEC = 20
    audio_dest = os.path.join(public_dir, "podcast.wav")
    print(f"Audio konvertieren → podcast.wav (+{AUDIO_PAD_SEC}s trailing silence)...")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", audio_path,
        "-af", f"apad=pad_dur={AUDIO_PAD_SEC}",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        audio_dest
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg Fehler: {result.stderr}")
        sys.exit(1)

    # WhisperX JSON kopieren (Remotion erwartet podcast.whisperx.json)
    json_dest = os.path.join(public_dir, "podcast.whisperx.json")
    shutil.copy2(whisperx_path, json_dest)
    print(f"WhisperX JSON → podcast.whisperx.json")

    # SRT kopieren (für caption-ducking; leere Datei wenn nicht vorhanden)
    srt_dest = os.path.join(public_dir, "podcast.srt")
    if srt_path and os.path.exists(srt_path):
        shutil.copy2(srt_path, srt_dest)
        print(f"SRT → podcast.srt")
    else:
        # Leere SRT damit Remotion nicht abstürzt
        with open(srt_dest, "w") as f:
            f.write("")

    # Audiodauer ermitteln (nur für Logging — Remotion's calculateMetadata
    # in Root.tsx liest die echte Dauer selbst aus public/podcast.wav).
    if duration_frames is None:
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_dest
        ], capture_output=True, text=True)
        duration_sec = float(probe.stdout.strip()) if probe.returncode == 0 else 180
        duration_frames = int(duration_sec * 30) + 60

    # Output-Pfad (absolut, da Remotion mit cwd=REMOTION_DIR läuft)
    if output_path is None:
        stem = Path(audio_path).stem
        out_dir = os.path.join(REMOTION_DIR, "out")
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, f"{stem}-{viz_type}.mp4")
    output_path = os.path.realpath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    COMPOSITION_MAP = {
        "dialogue": "Podcast-Dialogue",
        "monologue": "Podcast-Monologue",
    }
    composition_id = COMPOSITION_MAP.get(viz_type, "Podcast-Dialogue")

    props = {
        "vizMode": viz_type,
        "title": title,
        "episode": episode,
        "showName": show_name,
    }

    print(f"Rendern: {composition_id} → {output_path}")
    print(f"  {duration_frames} Frames @ 30fps = {duration_frames/30:.1f}s")

    cmd = [
        "npx", "--yes", "remotion", "render",
        "src/Root.tsx", composition_id, output_path,
        f"--props={__import__('json').dumps(props)}",
        "--log=verbose",
    ]

    result = subprocess.run(cmd, cwd=REMOTION_DIR, text=True)
    if result.returncode != 0:
        print(f"Remotion Fehler (Exit {result.returncode})")
        sys.exit(1)

    print(f"\n✓ Video gerendert: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remotion-Video rendern")
    parser.add_argument("audio", help="Audio-Datei")
    parser.add_argument("--whisperx", required=True, help="WhisperX JSON")
    parser.add_argument("--srt", help="SRT-Datei (optional)")
    parser.add_argument("--output", "-o", help="Output MP4-Pfad")
    parser.add_argument("--viz", default="dialogue", choices=["dialogue", "monologue"])
    parser.add_argument("--title", default="Podcast Episode")
    parser.add_argument("--episode", default="EP 01")
    parser.add_argument("--show-name", default="Signal")
    args = parser.parse_args()

    render(
        audio_path=args.audio,
        whisperx_path=args.whisperx,
        srt_path=args.srt,
        output_path=args.output,
        viz_type=args.viz,
        title=args.title,
        episode=args.episode,
        show_name=args.show_name,
    )
