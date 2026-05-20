#!/usr/bin/env python3
"""Mock pipeline.py — emits a fixed stdout script then exits 0.

Used by tests that need a subprocess to attach to without running the real pipeline.
"""
import sys
import time

SCRIPT = [
    ("─" * 60, 0),
    ("SCHRITT 1: Transkription", 0),
    ("─" * 60, 0),
    ("[1/4] Modell laden (large-v3-turbo, de)", 0.05),
    ("[2/4] Transkribieren", 0.05),
    ("[3/4] Wort-Alignment", 0.05),
    ("✓ Transkription fertig", 0.05),
    ("", 0),
    ("─" * 60, 0),
    ("SCHRITT 3: Video rendern (Remotion)", 0.05),
    ("─" * 60, 0),
    ("Rendering 50.0%", 0.05),
    ("Rendering 100.0%", 0.05),
    ("✓ Render fertig", 0.05),
]

for line, delay in SCRIPT:
    print(line, flush=True)
    if delay:
        time.sleep(delay)

sys.exit(0)
