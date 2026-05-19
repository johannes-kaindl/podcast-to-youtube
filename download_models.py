#!/usr/bin/env python3
"""
Alle Pipeline-Modelle vorab herunterladen für vollständigen Offline-Betrieb.
Einmalig ausführen — danach läuft die Pipeline ohne Internetverbindung
(außer YouTube-Upload).

Usage:
  python download_models.py                         # Whisper + Alignment (de, en)
  python download_models.py --hf-token hf_xxx       # + pyannote Diarization
  python download_models.py --languages de en fr    # Alignment für mehrere Sprachen
  python download_models.py --whisper-models base large-v3-turbo  # Nur bestimmte Modelle
"""
import argparse
import os
import sys

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]
DEFAULT_LANGUAGES = ["de", "en"]
PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"


def download_whisper(model_sizes: list[str]) -> None:
    import whisperx
    print(f"\n{'─' * 60}")
    print(f"Whisper-Modelle ({len(model_sizes)} Stück)")
    print(f"{'─' * 60}")
    for size in model_sizes:
        print(f"  → {size} laden ...", end=" ", flush=True)
        try:
            whisperx.load_model(size, device="cpu", compute_type="int8")
            print("✓")
        except Exception as e:
            print(f"✗ Fehler: {e}")


def download_alignment(languages: list[str]) -> None:
    import whisperx
    print(f"\n{'─' * 60}")
    print(f"Alignment-Modelle ({', '.join(languages)})")
    print(f"{'─' * 60}")
    # Dummy-Audio für load_align_model (braucht nur language_code)
    for lang in languages:
        print(f"  → Alignment {lang} ...", end=" ", flush=True)
        try:
            whisperx.load_align_model(language_code=lang, device="cpu")
            print("✓")
        except Exception as e:
            print(f"✗ Fehler: {e}")


def download_pyannote(hf_token: str) -> None:
    print(f"\n{'─' * 60}")
    print("pyannote Speaker-Diarization")
    print(f"{'─' * 60}")
    print("  Voraussetzung: Terms auf huggingface.co akzeptiert")
    print(f"  → {PYANNOTE_MODEL} laden ...", end=" ", flush=True)
    try:
        from pyannote.audio import Pipeline
        Pipeline.from_pretrained(PYANNOTE_MODEL, use_auth_token=hf_token)
        print("✓")
        print("  Modell gecacht — ab jetzt offline ohne Token nutzbar.")
    except Exception as e:
        print(f"✗ Fehler: {e}")
        if "gated" in str(e).lower() or "403" in str(e):
            print()
            print("  Terms noch nicht akzeptiert. Bitte aufrufen:")
            print(f"  https://huggingface.co/{PYANNOTE_MODEL}")
            print("  → Einloggen → 'Agree and access repository'")


def check_cached() -> None:
    """Zeigt welche Modelle bereits gecacht sind."""
    import whisperx  # noqa: F401 — trigger HF_HOME setup
    cache_dir = os.path.expanduser("~/.cache/whisper")
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    hub_dir = os.path.join(hf_home, "hub")

    print(f"\n{'─' * 60}")
    print("Cache-Status")
    print(f"{'─' * 60}")
    print(f"  Whisper-Cache:    {cache_dir}")
    print(f"  HuggingFace-Hub:  {hub_dir}")
    print()

    print("  Whisper-Modelle:")
    for size in WHISPER_MODELS:
        pt_file = os.path.join(cache_dir, f"{size}.pt")
        status = "✓ gecacht" if os.path.exists(pt_file) else "✗ fehlt"
        size_info = ""
        if os.path.exists(pt_file):
            mb = os.path.getsize(pt_file) / 1024 / 1024
            size_info = f" ({mb:.0f} MB)"
        print(f"    {size:<20} {status}{size_info}")

    print()
    print("  pyannote Diarization:")
    model_slug = PYANNOTE_MODEL.replace("/", "--")
    model_dir = os.path.join(hub_dir, f"models--{model_slug}")
    if os.path.isdir(model_dir):
        print(f"    ✓ gecacht  ({model_dir})")
    else:
        print(f"    ✗ fehlt    (--hf-token benötigt + Terms akzeptieren)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline-Modelle für Offline-Betrieb herunterladen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--whisper-models", nargs="+", default=WHISPER_MODELS,
        metavar="MODEL",
        help=f"Whisper-Modelle (Standard: alle). Optionen: {', '.join(WHISPER_MODELS)}",
    )
    parser.add_argument(
        "--languages", nargs="+", default=DEFAULT_LANGUAGES,
        metavar="LANG",
        help="Sprachen für Alignment-Modelle (Standard: de en)",
    )
    parser.add_argument(
        "--hf-token", default=os.environ.get("HF_TOKEN"),
        help="HuggingFace-Token für pyannote (oder HF_TOKEN env-Variable)",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Nur Cache-Status anzeigen, nichts herunterladen",
    )
    args = parser.parse_args()

    print("Pipeline-Modelle — Offline-Setup")
    print("=" * 60)

    check_cached()

    if args.status:
        return

    download_whisper(args.whisper_models)
    download_alignment(args.languages)

    if args.hf_token:
        download_pyannote(args.hf_token)
    else:
        print(f"\n{'─' * 60}")
        print("pyannote übersprungen (kein --hf-token / HF_TOKEN)")
        print("  Zum Herunterladen:")
        print("  python download_models.py --hf-token hf_xxx")

    print(f"\n{'═' * 60}")
    print("Fertig. Cache-Status nach Download:")
    check_cached()


if __name__ == "__main__":
    main()
