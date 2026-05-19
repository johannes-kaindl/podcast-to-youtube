#!/usr/bin/env python3
"""
Interaktives Full-Screen TUI für die Podcast-Pipeline.

Usage:
  python tui.py                  # Startet ohne vorausgefüllten Pfad
  python tui.py podcast.m4a      # Pre-fills Audio-Pfad
"""
import sys

from tui_app import PipelineTUI


def main() -> None:
    initial_audio = sys.argv[1] if len(sys.argv) > 1 else ""
    PipelineTUI(initial_audio=initial_audio).run()


if __name__ == "__main__":
    main()
