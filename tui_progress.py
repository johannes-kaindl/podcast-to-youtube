"""Progress tracking — maps pipeline stdout lines to step + overall percentage."""
import re
from dataclasses import dataclass

STEP_MARKERS = [
    (re.compile(r"SCHRITT 1:"),               1, "Schritt 1/4 · Transkription",          2),
    (re.compile(r"\[1/4\] Modell"),           1, "Schritt 1/4 · Modell laden …",         5),
    (re.compile(r"\[2/4\] Transkrib"),        1, "Schritt 1/4 · Transkribieren …",       15),
    (re.compile(r"\[3/4\] Wort"),             1, "Schritt 1/4 · Wort-Alignment …",       32),
    (re.compile(r"\[4/4\]"),                  1, "Schritt 1/4 · Speaker-Erkennung …",    39),
    (re.compile(r"SCHRITT 2:"),               2, "Schritt 2/4 · Metadaten generieren …", 44),
    (re.compile(r"Metadaten generieren via"), 2, "Schritt 2/4 · LLM generiert …",        47),
    (re.compile(r"SCHRITT 3:"),               3, "Schritt 3/4 · Video rendern …",        53),
    (re.compile(r"SCHRITT 4:"),               4, "Schritt 4/4 · YouTube-Upload …",       96),
]
RENDER_PCT_RE = re.compile(r"(\d+\.?\d*)%")


@dataclass
class ProgressEvent:
    progress: float
    label: str
    step: int


def match_line(line: str, current_step: int) -> ProgressEvent | None:
    for pattern, step, label, progress in STEP_MARKERS:
        if pattern.search(line):
            return ProgressEvent(progress, label, step)
    if current_step == 3:
        m = RENDER_PCT_RE.search(line)
        if m:
            pct = float(m.group(1))
            overall = 53.0 + pct * 42.0 / 100.0
            return ProgressEvent(overall, f"Schritt 3/4 · Rendering  {pct:.0f}%", 3)
    return None
