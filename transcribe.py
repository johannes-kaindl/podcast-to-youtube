#!/usr/bin/env python3
"""
WhisperX transcription with optional speaker diarization.
Outputs: {stem}.whisperx.json, {stem}.srt, {stem}.txt

Usage:
  python transcribe.py audio.m4a --output-dir ./output
  python transcribe.py audio.m4a --output-dir ./output --language en --hf-token hf_xxx
"""
import argparse
import json
import os
import sys


def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"


def _pyannote_is_cached() -> bool:
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    model_slug = PYANNOTE_MODEL.replace("/", "--")
    model_dir = os.path.join(hf_home, "hub", f"models--{model_slug}")
    return os.path.isdir(model_dir)


def transcribe(audio_path: str, output_dir: str, language: str = "de",
               model_size: str = "large-v3-turbo", hf_token: str | None = None,
               diarize: bool = True, num_speakers: int | None = None) -> dict:
    import whisperx

    device = "cpu"
    compute_type = "int8"

    print(f"[1/4] Modell laden ({model_size})...", flush=True)
    from faster_whisper import WhisperModel
    fw_model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print(f"[2/4] Transkribieren: {os.path.basename(audio_path)}", flush=True)
    audio = whisperx.load_audio(audio_path)
    fw_lang = None if language == "auto" else language
    segments_iter, info = fw_model.transcribe(
        audio_path, language=fw_lang, beam_size=5, vad_filter=True
    )
    detected_lang = info.language

    # Stream-Output: jedes Segment sofort drucken, sobald fertig
    segments: list[dict] = []
    for seg in segments_iter:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text})
        mins, secs = divmod(seg.start, 60)
        print(f"  [{int(mins):02d}:{secs:05.2f}] {seg.text.strip()}", flush=True)

    result = {"segments": segments, "language": detected_lang}
    print(f"      Sprache erkannt: {detected_lang}, {len(segments)} Segmente", flush=True)

    # Modell freigeben — Speicher sparen vor Alignment
    del fw_model

    print("[3/4] Wort-Alignment...", flush=True)
    model_a, metadata = whisperx.load_align_model(
        language_code=detected_lang, device=device
    )
    result = whisperx.align(result["segments"], model_a, metadata, audio, device,
                             return_char_alignments=False)

    cached = _pyannote_is_cached()
    can_diarize = diarize and (hf_token or cached)

    if can_diarize:
        speakers_info = f" ({num_speakers} Sprecher:innen)" if num_speakers else " (Auto)"
        offline_hint = " [offline/Cache]" if cached else ""
        print(f"[4/4] Speaker-Diarization (pyannote){speakers_info}{offline_hint}...")
        if cached:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from whisperx.diarize import DiarizationPipeline, assign_word_speakers
        diarize_model = DiarizationPipeline(token=hf_token or "", device=device)
        diarize_kwargs = {}
        if num_speakers is not None:
            diarize_kwargs["num_speakers"] = num_speakers
        diarize_segments = diarize_model(audio_path, **diarize_kwargs)
        result = assign_word_speakers(diarize_segments, result)
        for seg in result["segments"]:
            if "speaker" not in seg:
                first_speaker = next(
                    (w.get("speaker") for w in seg.get("words", []) if "speaker" in w),
                    "SPEAKER_00"
                )
                seg["speaker"] = first_speaker
    else:
        if not diarize:
            print("[4/4] Diarization deaktiviert")
        else:
            print("[4/4] Diarization übersprungen (kein HF-Token, Modell nicht gecacht)")
            print("      → python download_models.py --hf-token $HF_TOKEN")
        for seg in result["segments"]:
            seg.setdefault("speaker", "SPEAKER_00")

    stem = os.path.splitext(os.path.basename(audio_path))[0]
    os.makedirs(output_dir, exist_ok=True)

    # WhisperX JSON (für Remotion)
    json_path = os.path.join(output_dir, f"{stem}.whisperx.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  → {json_path}")

    # SRT (für Remotion caption-ducking)
    srt_path = os.path.join(output_dir, f"{stem}.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result["segments"], 1):
            speaker = seg.get("speaker", "SPEAKER_00")
            text = f"[{speaker}] {seg['text'].strip()}"
            f.write(f"{i}\n"
                    f"{format_srt_time(seg['start'])} --> {format_srt_time(seg['end'])}\n"
                    f"{text}\n\n")
    print(f"  → {srt_path}")

    # Plain-text Transkript mit Speaker-Labels
    txt_path = os.path.join(output_dir, f"{stem}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        current_speaker = None
        for seg in result["segments"]:
            speaker = seg.get("speaker", "SPEAKER_00")
            if speaker != current_speaker:
                current_speaker = speaker
                f.write(f"\n{speaker}:\n")
            f.write(seg["text"].strip() + " ")
        f.write("\n")
    print(f"  → {txt_path}")

    return {
        "json": json_path,
        "srt": srt_path,
        "txt": txt_path,
        "language": detected_lang,
        "segments": len(result["segments"]),
        "has_diarization": can_diarize,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WhisperX Transkription")
    parser.add_argument("audio", help="Audio-Datei (m4a/mp3/wav)")
    parser.add_argument("--output-dir", "-o", default="./output")
    parser.add_argument("--language", "-l", default="de",
                        help="Sprachcode: de, en, auto")
    parser.add_argument("--model", "-m", default="large-v3-turbo",
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3",
                                 "large-v3-turbo"])
    parser.add_argument("--hf-token", help="HuggingFace-Token für Diarization")
    parser.add_argument("--no-diarize", action="store_true",
                        help="Speaker-Diarization deaktivieren")
    parser.add_argument("--speakers", type=int, default=None,
                        help="Exakte Anzahl Sprecher:innen (leer = Auto)")
    args = parser.parse_args()

    result = transcribe(
        audio_path=args.audio,
        output_dir=args.output_dir,
        language=args.language,
        model_size=args.model,
        hf_token=args.hf_token or os.environ.get("HF_TOKEN"),
        diarize=not args.no_diarize,
        num_speakers=args.speakers,
    )
    print(f"\n✓ {result['segments']} Segmente, Sprache={result['language']}, "
          f"Diarization={'ja' if result['has_diarization'] else 'nein'}")
