#!/usr/bin/env python3
"""
Vollautomatische Podcast-zu-YouTube-Pipeline.

Schritte:
  1. Transkription (WhisperX)
  2. YouTube-Metadaten generieren (Claude API)
  3. Video rendern (Remotion)
  4. Upload zu YouTube (als Private)

Usage:
  python pipeline.py podcast.m4a
  python pipeline.py podcast.m4a --skip-upload --viz ring
  python pipeline.py podcast.m4a --hf-token hf_xxx --language en
  python pipeline.py podcast.m4a --show-name "Mein Podcast" --episode "EP 42"
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Lokale Module
sys.path.insert(0, os.path.dirname(__file__))


# ── Run-State-Persistenz ────────────────────────────────────────────────────
#
# Jeder Run hinterlässt eine run-state.json im Output-Ordner. Die TUI liest sie
# beim Audio-Path-Change und entscheidet daraus:
#   • welche Phasen sind schon "done" und können automatisch geskippt werden
#   • ob ein "running" oder "aborted" Run zur Wiederaufnahme angeboten wird
#
# Phasen-Status (Mealy-Maschine):
#   pending  → running  → done       (erfolgreich abgeschlossen)
#                       → aborted    (Exception oder Subprocess-Exit≠0)
#                       → (running, wenn Pipeline extern gekillt wird → kein
#                          finalisierender done/aborted-Schritt mehr)
#   pending  → skipped                (skip_* gesetzt, Phase nie betreten)
RUN_STATE_FILE = "run-state.json"
RUN_STATE_SCHEMA = 1
PHASES = ("transcribe", "meta", "render", "upload")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state_path(output_dir: str) -> str:
    return os.path.join(output_dir, RUN_STATE_FILE)


def _load_state(output_dir: str) -> dict | None:
    path = _state_path(output_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_state(output_dir: str, state: dict) -> None:
    state["updated_at"] = _now_iso()
    path = _state_path(output_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _init_state(output_dir: str, audio_path: str, config_dict: dict) -> dict:
    """Lädt existierenden State oder erzeugt neuen; mergt aktuelle Config."""
    state = _load_state(output_dir) or {
        "schema_version": RUN_STATE_SCHEMA,
        "audio": audio_path,
        "stem": Path(audio_path).stem,
        "started_at": _now_iso(),
        "phases": {p: {"status": "pending"} for p in PHASES},
    }
    state["audio"] = audio_path
    state["config"] = config_dict
    _save_state(output_dir, state)
    return state


def _set_phase(state: dict, output_dir: str, phase: str,
               status: str, **extra) -> None:
    entry: dict = {"status": status, **extra}
    # historische Felder (started_at etc.) der vorigen Iteration nicht
    # versehentlich überschreiben — nur ergänzen
    prev = state["phases"].get(phase, {})
    if status == "running":
        entry.setdefault("started_at", _now_iso())
    elif status in ("done", "aborted", "skipped"):
        entry.setdefault("started_at", prev.get("started_at", _now_iso()))
        entry["finished_at"] = _now_iso()
    state["phases"][phase] = entry
    _save_state(output_dir, state)


def _phase_done(state: dict, phase: str) -> bool:
    return state["phases"].get(phase, {}).get("status") == "done"


def run_pipeline(audio_path: str, output_dir: str, show_name: str = "Signal",
                 episode: str = "EP 01", language: str = "de", model: str = "large-v3-turbo",
                 hf_token: str | None = None, viz_type: str = "dialogue",
                 diarize: bool = True, num_speakers: int | None = None,
                 skip_transcribe: bool = False, skip_meta: bool = False,
                 skip_render: bool = False, skip_upload: bool = False,
                 privacy: str = "private") -> dict:

    stem = Path(audio_path).stem
    os.makedirs(output_dir, exist_ok=True)

    state = _init_state(output_dir, audio_path, {
        "show_name": show_name, "episode": episode, "language": language,
        "model": model, "viz_type": viz_type, "diarize": diarize,
        "num_speakers": num_speakers, "privacy": privacy,
        "skip_transcribe": skip_transcribe, "skip_meta": skip_meta,
        "skip_render": skip_render, "skip_upload": skip_upload,
    })

    results = {}

    # ── Schritt 1: Transkription ─────────────────────────────────────────────
    json_path = os.path.join(output_dir, f"{stem}.whisperx.json")
    srt_path = os.path.join(output_dir, f"{stem}.srt")
    txt_path = os.path.join(output_dir, f"{stem}.txt")

    if not skip_transcribe:
        print("\n" + "─" * 60)
        print("SCHRITT 1: Transkription")
        print("─" * 60)
        _set_phase(state, output_dir, "transcribe", "running")
        try:
            from transcribe import transcribe
            results["transcription"] = transcribe(
                audio_path=audio_path,
                output_dir=output_dir,
                language=language,
                model_size=model,
                hf_token=hf_token or os.environ.get("HF_TOKEN"),
                diarize=diarize,
                num_speakers=num_speakers,
            )
            _set_phase(state, output_dir, "transcribe", "done",
                       segments=results["transcription"].get("segments"),
                       detected_language=results["transcription"].get("language"),
                       files=[
                           os.path.basename(json_path),
                           os.path.basename(srt_path),
                           os.path.basename(txt_path),
                       ])
        except Exception as e:
            _set_phase(state, output_dir, "transcribe", "aborted",
                       error=f"{type(e).__name__}: {e}")
            raise
    else:
        if not os.path.exists(txt_path):
            print(f"FEHLER: --skip-transcribe gesetzt aber {txt_path} fehlt")
            _set_phase(state, output_dir, "transcribe", "aborted",
                       error=f"--skip-transcribe ohne {os.path.basename(txt_path)}")
            sys.exit(1)
        print(f"Transkription übersprungen (nutze bestehende Dateien in {output_dir})")
        if not _phase_done(state, "transcribe"):
            _set_phase(state, output_dir, "transcribe", "skipped",
                       note="Files präsent, Phase nicht ausgeführt")

    # ── Schritt 2: Metadaten generieren ──────────────────────────────────────
    meta_json_path = os.path.join(output_dir, f"{stem}.youtube-meta.json")

    if not skip_meta:
        print("\n" + "─" * 60)
        print("SCHRITT 2: YouTube-Metadaten generieren")
        print("─" * 60)
        _set_phase(state, output_dir, "meta", "running")
        try:
            from generate_meta import generate_metadata
            results["meta"] = generate_metadata(
                txt_path=txt_path,
                whisperx_path=json_path if os.path.exists(json_path) else None,
                show_name=show_name,
                episode=episode,
                output_dir=output_dir,
                language=language,
            )
            _set_phase(state, output_dir, "meta", "done",
                       title=results["meta"].get("title"),
                       files=[
                           os.path.basename(meta_json_path),
                           os.path.basename(meta_json_path).replace(".json", ".md"),
                       ])
        except Exception as e:
            _set_phase(state, output_dir, "meta", "aborted",
                       error=f"{type(e).__name__}: {e}")
            raise
    else:
        if os.path.exists(meta_json_path):
            with open(meta_json_path, encoding="utf-8") as f:
                results["meta"] = json.load(f)
        print("Metadaten-Generierung übersprungen")
        if not _phase_done(state, "meta"):
            _set_phase(state, output_dir, "meta", "skipped",
                       note="Phase nicht ausgeführt")

    meta = results.get("meta", {})

    # ── Schritt 3: Video rendern ──────────────────────────────────────────────
    video_path = os.path.join(output_dir, f"{stem}-{viz_type}.mp4")

    if not skip_render:
        print("\n" + "─" * 60)
        print("SCHRITT 3: Video rendern (Remotion)")
        print("─" * 60)
        _set_phase(state, output_dir, "render", "running", viz_type=viz_type)
        try:
            from render_video import render
            video_path = render(
                audio_path=audio_path,
                whisperx_path=json_path,
                srt_path=srt_path if os.path.exists(srt_path) else None,
                output_path=video_path,
                viz_type=viz_type,
                title=meta.get("title", stem),
                episode=episode,
                show_name=show_name,
            )
            results["video"] = video_path
            _set_phase(state, output_dir, "render", "done",
                       viz_type=viz_type, output=os.path.basename(video_path),
                       size_mb=round(os.path.getsize(video_path) / 1024**2, 1))
        except SystemExit as e:
            # render_video.py ruft sys.exit(1) bei Remotion-Fehler
            _set_phase(state, output_dir, "render", "aborted",
                       viz_type=viz_type, error=f"render exit {e.code}")
            raise
        except Exception as e:
            _set_phase(state, output_dir, "render", "aborted",
                       viz_type=viz_type, error=f"{type(e).__name__}: {e}")
            raise
    else:
        print(f"Rendering übersprungen")
        if os.path.exists(video_path):
            results["video"] = video_path
        if not _phase_done(state, "render"):
            _set_phase(state, output_dir, "render", "skipped",
                       viz_type=viz_type, note="Phase nicht ausgeführt")

    # ── Schritt 4: YouTube-Upload ─────────────────────────────────────────────
    if not skip_upload and results.get("video"):
        print("\n" + "─" * 60)
        print("SCHRITT 4: YouTube-Upload")
        print("─" * 60)
        _set_phase(state, output_dir, "upload", "running")
        try:
            from upload_youtube import upload
            results["youtube"] = upload(
                video_path=results["video"],
                title=meta.get("title", stem),
                description=meta.get("description", ""),
                tags=meta.get("tags", []),
                category_id=meta.get("category_id", "27"),
                language=meta.get("language", "de"),
                privacy=privacy,
                show_name=meta.get("show_name", show_name),
            )
            _set_phase(state, output_dir, "upload", "done",
                       url=results["youtube"].get("url"),
                       video_id=results["youtube"].get("id"),
                       privacy=privacy)
        except Exception as e:
            _set_phase(state, output_dir, "upload", "aborted",
                       error=f"{type(e).__name__}: {e}")
            raise
    else:
        if skip_upload:
            print("\nYouTube-Upload übersprungen (--skip-upload)")
            if not _phase_done(state, "upload"):
                _set_phase(state, output_dir, "upload", "skipped",
                           note="--skip-upload")

    # ── Zusammenfassung ────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("FERTIG")
    print("═" * 60)
    if results.get("transcription"):
        t = results["transcription"]
        print(f"  Transkript: {t['segments']} Segmente, Sprache={t['language']}")
    if results.get("meta"):
        print(f"  Titel: {results['meta'].get('title', '—')}")
    if results.get("video"):
        size_mb = os.path.getsize(results["video"]) / 1024**2
        print(f"  Video: {results['video']} ({size_mb:.1f} MB)")
    if results.get("youtube"):
        print(f"  YouTube: {results['youtube']['url']}")
    print()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Podcast-zu-YouTube Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Beispiele:
  # Vollständige Pipeline
  python pipeline.py podcast.m4a

  # Nur Transkription + Rendering (kein Upload)
  python pipeline.py podcast.m4a --skip-upload

  # Mit Speaker-Diarization
  python pipeline.py podcast.m4a --hf-token hf_xxx

  # Englischer Podcast, Ring-Visualizer
  python pipeline.py podcast.m4a --language en --viz ring --episode "EP 42"

  # Gespräch mit 2 Sprechern — Dialogue-View (Teleprompter + Ring, kein Upload)
  python pipeline.py podcast.m4a --viz dialogue --skip-upload

  # Monologue-View (zentrierter Ring + Karaoke-Caption)
  python pipeline.py podcast.m4a --viz monologue --skip-upload
"""
    )
    parser.add_argument("audio", help="Audio-Datei (.m4a/.mp3/.wav)")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output-Ordner (Standard: ./output/<dateiname>/)")
    parser.add_argument("--show-name", default="Signal", help="Podcast-Serienname")
    parser.add_argument("--episode", default="EP 01", help="Episodennummer")
    parser.add_argument("--language", "-l", default="de", help="Sprachcode: de, en, auto")
    parser.add_argument("--model", "-m", default="large-v3-turbo",
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3",
                                 "large-v3-turbo"],
                        help="Whisper-Modell")
    parser.add_argument("--hf-token", help="HuggingFace-Token für Speaker-Diarization")
    parser.add_argument("--no-diarize", action="store_true",
                        help="Speaker-Diarization deaktivieren (Monolog)")
    parser.add_argument("--speakers", type=int, default=None,
                        help="Exakte Anzahl Sprecher:innen (leer = Auto)")
    parser.add_argument("--viz", default="dialogue",
                        choices=["dialogue", "monologue"],
                        help="Visualizer-Typ (dialogue/monologue für Gespräche mit Karaoke-Teleprompter)")
    parser.add_argument("--privacy", default="private",
                        choices=["private", "unlisted"],
                        help="YouTube-Sichtbarkeit nach Upload")
    parser.add_argument("--skip-transcribe", action="store_true",
                        help="Transkription überspringen (nutzt bestehende Dateien)")
    parser.add_argument("--skip-meta", action="store_true",
                        help="Metadaten-Generierung überspringen")
    parser.add_argument("--skip-render", action="store_true",
                        help="Video-Rendering überspringen")
    parser.add_argument("--skip-upload", action="store_true",
                        help="YouTube-Upload überspringen")
    args = parser.parse_args()

    stem = Path(args.audio).stem
    output_dir = args.output_dir or os.path.join(
        os.path.dirname(__file__), "output", stem
    )

    run_pipeline(
        audio_path=args.audio,
        output_dir=output_dir,
        show_name=args.show_name,
        episode=args.episode,
        language=args.language,
        model=args.model,
        hf_token=args.hf_token or os.environ.get("HF_TOKEN"),
        viz_type=args.viz,
        diarize=not args.no_diarize,
        num_speakers=args.speakers,
        skip_transcribe=args.skip_transcribe,
        skip_meta=args.skip_meta,
        skip_render=args.skip_render,
        skip_upload=args.skip_upload,
        privacy=args.privacy,
    )


if __name__ == "__main__":
    main()
