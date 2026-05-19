"""Pipeline TUI — App, compose, event routing. Heavy lifting in tui_cmd / tui_progress."""
import json
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label,
    ProgressBar, RichLog, Rule, Select, Static,
)

from tui_cmd import (
    PipelineConfig, build_command, can_diarize, is_pyannote_cached,
    resolve_audio_path,
)
from tui_progress import match_line

PIPELINE_DIR = Path(__file__).parent
RUN_STATE_FILE = "run-state.json"
PHASE_LABELS = {
    "transcribe": "Transkription",
    "meta": "Metadaten",
    "render": "Rendering",
    "upload": "Upload",
}


def _stem_to_title(path: str) -> str:
    return Path(path).stem.replace("_", " ")


class PipelineTUI(App[None]):
    TITLE = "Podcast Pipeline"
    SUB_TITLE = "Transkription · Meta · Render · Upload"
    CSS_PATH = "tui.tcss"

    BINDINGS = [
        ("ctrl+r", "run_pipeline", "Starten"),
        ("ctrl+y", "copy_log", "Log → Clipboard"),
        ("ctrl+q", "quit", "Beenden"),
    ]

    def __init__(self, initial_audio: str = "") -> None:
        super().__init__()
        self._initial_audio = initial_audio
        self._pipeline_active = False
        self._auto_title = _stem_to_title(initial_audio) if initial_audio else ""
        self._start_time: float = 0.0
        self._current_progress: float = 0.0
        self._current_step: int = 0
        self._current_stem: str = ""

    # ── Compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="config-panel"):
                with VerticalScroll(id="config-scroll"):
                    yield from self._compose_config_fields()
                yield Button("▶  Pipeline starten", id="run-btn")
            yield RichLog(id="log-panel", highlight=True, markup=True, wrap=True)
        with Horizontal(id="progress-area"):
            yield Static("Bereit.", id="step-label")
            yield ProgressBar(total=100, show_eta=False, show_percentage=True, id="progress-bar")
            yield Static("", id="time-label")
        yield Footer()

    def _compose_config_fields(self) -> ComposeResult:
        yield Static("", id="resume-banner", classes="resume-banner hidden", markup=True)
        yield Label("Audio-Datei  (.m4a / .mp3 / .wav)", classes="field-label")
        yield Input(
            value=self._initial_audio,
            placeholder="/Pfad/zu/podcast.m4a",
            id="audio-path",
        )

        yield Label("Visualizer", classes="field-label")
        yield Select(
            [
                ("Dialogue — Teleprompter + Ring + Waveform", "dialogue"),
                ("Monologue — Großer Ring + Caption + Waveform", "monologue"),
            ],
            value="dialogue",
            id="viz-type",
        )

        with Horizontal(id="lang-model"):
            with Vertical():
                yield Label("Sprache", classes="field-label")
                yield Select(
                    [
                        ("Auto", "auto"),
                        ("Deutsch (de)", "de"),
                        ("Englisch (en)", "en"),
                    ],
                    value="auto",
                    id="language",
                )
            with Vertical():
                yield Label("Modell", classes="field-label")
                yield Select(
                    [
                        ("large-v3-turbo", "large-v3-turbo"),
                        ("large-v3", "large-v3"),
                        ("large-v2", "large-v2"),
                        ("medium", "medium"),
                        ("small", "small"),
                        ("base", "base"),
                        ("tiny", "tiny"),
                    ],
                    value="large-v3-turbo",
                    id="model",
                )

        yield Label("Sprecher-Erkennung", classes="field-label")
        yield Select(
            [
                ("Auto — Anzahl erkennen", "auto"),
                ("2 Sprecher:innen", "2"),
                ("3 Sprecher:innen", "3"),
                ("4 Sprecher:innen", "4"),
                ("5 Sprecher:innen", "5"),
                ("Aus — Monolog / kein Token", "off"),
            ],
            value="auto",
            id="diarize",
        )

        yield Label("Episode / Titel", classes="field-label")
        yield Input(value=self._auto_title or "EP 01", id="episode")

        yield Label("Kanal / Serienname", classes="field-label")
        yield Input(value="Signal", id="show-name")

        yield Rule(line_style="heavy")
        yield Checkbox("Transkription überspringen", id="skip-transcribe")
        yield Checkbox("Metadaten überspringen", id="skip-meta")
        yield Checkbox("Rendering überspringen", id="skip-render")
        yield Checkbox("Upload überspringen", value=True, id="skip-upload")

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write(
            "[dim]Audio-Pfad eingeben, Optionen wählen, dann "
            "[bold]▶ Pipeline starten[/] oder [bold]Ctrl+R[/].[/]"
        )
        self.set_interval(1.0, self._tick_timer)
        if self._initial_audio:
            self._apply_run_state_for(self._initial_audio)
            self.query_one("#run-btn", Button).focus()
        else:
            self.query_one("#audio-path", Input).focus()

    def _tick_timer(self) -> None:
        if not self._pipeline_active or self._start_time == 0:
            return
        elapsed = int(time.time() - self._start_time)
        m, s = divmod(elapsed, 60)
        self.query_one("#time-label", Static).update(f"⏱ {m}:{s:02d}")

    # ── Events ─────────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "audio-path":
            return
        path = event.value.strip()
        if not path:
            self._hide_resume_banner()
            return
        episode_input = self.query_one("#episode", Input)
        derived = _stem_to_title(path)
        if episode_input.value in ("EP 01", self._auto_title):
            episode_input.value = derived
            self._auto_title = derived
        # State scannen und UI an vorhandenen Run anpassen
        self._apply_run_state_for(path)

    # ── Run-State / Resume ─────────────────────────────────────────────────

    def _output_dir_for(self, audio_path: str) -> Path:
        return PIPELINE_DIR / "output" / Path(audio_path).stem

    def _load_run_state(self, audio_path: str) -> dict | None:
        state_path = self._output_dir_for(audio_path) / RUN_STATE_FILE
        if not state_path.exists():
            return None
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _apply_run_state_for(self, audio_path: str) -> None:
        """Lies run-state.json, hake done-Phasen ab, zeige Resume-Banner."""
        state = self._load_run_state(audio_path)
        if state is None:
            self._hide_resume_banner()
            # Bei neuem Audio: Skip-Boxes auf User-Default zurücksetzen (alle aus
            # außer skip-upload, der default-true ist). Nur wenn Pipeline nicht
            # gerade läuft — sonst überschreibt das die User-Auswahl mitten drin.
            if not self._pipeline_active:
                for box_id, default in [
                    ("skip-transcribe", False), ("skip-meta", False),
                    ("skip-render", False), ("skip-upload", True),
                ]:
                    try:
                        self.query_one(f"#{box_id}", Checkbox).value = default
                    except Exception:
                        pass
            return

        phases = state.get("phases", {})
        # Auto-Skip-Logik: Phasen, die bereits done oder explizit skipped sind,
        # werden vorab angehakt. Pending/running/aborted-Phasen fallen auf den
        # User-Default zurück (Upload default-True bleibt damit User-sicher).
        if not self._pipeline_active:
            defaults = {
                "skip-transcribe": False, "skip-meta": False,
                "skip-render": False, "skip-upload": True,
            }
            phase_to_box = {
                "transcribe": "skip-transcribe", "meta": "skip-meta",
                "render": "skip-render", "upload": "skip-upload",
            }
            for phase, box_id in phase_to_box.items():
                status = phases.get(phase, {}).get("status")
                if status in ("done", "skipped"):
                    value = True
                else:
                    value = defaults[box_id]
                try:
                    self.query_one(f"#{box_id}", Checkbox).value = value
                except Exception:
                    pass

        self._render_resume_banner(state)

    def _render_resume_banner(self, state: dict) -> None:
        phases = state.get("phases", {})
        # Welche Phase ist die zuletzt aktive (running / aborted)?
        aborted_phase = None
        running_phase = None
        for name in ("transcribe", "meta", "render", "upload"):
            status = phases.get(name, {}).get("status")
            if status == "running":
                running_phase = name
            elif status == "aborted":
                aborted_phase = name

        banner = self.query_one("#resume-banner", Static)
        banner.remove_class("hidden")
        banner.remove_class("done")
        banner.remove_class("aborted")

        # Phase-Übersicht als kompakte Glyph-Zeile
        glyphs = []
        for name in ("transcribe", "meta", "render", "upload"):
            s = phases.get(name, {}).get("status", "pending")
            icon = {
                "done": "✓", "running": "⟳", "aborted": "✗",
                "skipped": "·", "pending": "○",
            }.get(s, "?")
            glyphs.append(f"{icon} {PHASE_LABELS[name]}")
        overview = "  ".join(glyphs)

        if aborted_phase or running_phase:
            phase = aborted_phase or running_phase
            label = "abgebrochen" if aborted_phase else "läuft / extern beendet"
            err = phases.get(phase, {}).get("error", "")
            err_line = f"\n[dim]Fehler: {err}[/]" if err else ""
            banner.update(
                f"[bold]🔄 Letzter Run: [yellow]{PHASE_LABELS[phase]}[/] {label}.[/]\n"
                f"[dim]{overview}[/]{err_line}\n"
                f"[dim]Skip-Boxes für abgeschlossene Phasen vorab angehakt → "
                f"'Pipeline starten' nimmt nahtlos wieder auf.[/]"
            )
            banner.add_class("aborted")
        elif all(phases.get(p, {}).get("status") in ("done", "skipped")
                 for p in ("transcribe", "meta", "render", "upload")):
            banner.update(
                f"[bold green]✓ Letzter Run komplett.[/]\n"
                f"[dim]{overview}[/]\n"
                f"[dim]Skip-Boxes alle angehakt — Start würde direkt fertig sein. "
                f"Für Neu-Render: Render-Skip entfernen.[/]"
            )
            banner.add_class("done")
        else:
            # Mixed / unfinished pending — zeig Übersicht
            banner.update(
                f"[bold]Vorhandener Run gefunden.[/]\n[dim]{overview}[/]"
            )

    def _hide_resume_banner(self) -> None:
        try:
            banner = self.query_one("#resume-banner", Static)
            banner.update("")
            banner.add_class("hidden")
        except Exception:
            pass

    def _refresh_resume_state_after_run(self) -> None:
        """Pipeline-Ende: state-File frisch lesen + Banner aktualisieren."""
        audio_input = self.query_one("#audio-path", Input)
        if audio_input.value.strip():
            self._apply_run_state_for(audio_input.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.action_run_pipeline()

    # ── Action: Pipeline starten ───────────────────────────────────────────

    def action_copy_log(self) -> None:
        log = self.query_one(RichLog)
        lines = [getattr(line, "text", str(line)) for line in log.lines]
        text = "\n".join(lines)
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)
            log.write(f"[dim green]✓ {len(lines)} Zeilen → Clipboard (Cmd+V)[/]")
        except Exception as e:
            log.write(f"[red]✗ Copy fehlgeschlagen: {e}[/]")

    def action_run_pipeline(self) -> None:
        log = self.query_one(RichLog)
        try:
            self._start_pipeline(log)
        except Exception as e:
            log.write(f"[bold red]✗ Start fehlgeschlagen: {type(e).__name__}: {e}[/]")
            for line in traceback.format_exc().splitlines():
                log.write(f"[dim red]{line}[/]")
            self._set_pipeline_active(False)

    def _start_pipeline(self, log: RichLog) -> None:
        if self._pipeline_active:
            return

        config = self._gather_config(log)
        if config is None:
            return

        if config.diarize != "off" and not config.skip_transcribe and not can_diarize():
            self._explain_diarize_missing(log)
            return  # harter Abbruch — User entscheidet bewusst

        cmd = build_command(config, PIPELINE_DIR)

        self._current_stem = Path(config.audio).stem
        self._start_time = time.time()
        self._current_progress = 0.0
        self._current_step = 0

        # Persistentes Log-File: output/<stem>/run-<timestamp>.log
        # Wird in _execute() befüllt; überlebt TUI-Kill/Crash und kann später
        # mit `tail -f` mitverfolgt werden.
        output_dir = PIPELINE_DIR / "output" / self._current_stem
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self._log_file_path: Path | None = output_dir / f"run-{timestamp}.log"

        pb = self.query_one("#progress-bar", ProgressBar)
        status = self.query_one("#step-label", Static)
        pb.update(progress=0)
        status.update("Startet …")

        log.clear()
        log.write(
            f"[bold #b8e986]▶ Starte Pipeline[/]\n"
            f"[dim]{' '.join(cmd)}[/]\n"
            f"[dim]Log → {self._log_file_path}[/]\n"
            f"[dim]{'─' * 60}[/]\n"
        )

        self._set_pipeline_active(True)
        self._execute(cmd)

    def _explain_diarize_missing(self, log: RichLog) -> None:
        import os
        token_set = bool(os.environ.get("HF_TOKEN"))
        cached = is_pyannote_cached()

        log.write("")
        log.write("[bold red]✗ Sprecher-Erkennung gewählt, aber nicht einsatzbereit.[/]")
        log.write("")
        log.write(f"  HF_TOKEN gesetzt:  {'[green]✓[/]' if token_set else '[red]✗[/]'}")
        log.write(f"  pyannote-Modell:   {'[green]✓ gecacht[/]' if cached else '[red]✗ fehlt[/]'}")
        log.write("")
        log.write("[bold]Einmaliges Setup:[/]")
        log.write("  1. Token: [cyan]https://huggingface.co/settings/tokens[/]")
        log.write("  2. Lizenz: [cyan]https://huggingface.co/pyannote/speaker-diarization-3.1[/]")
        log.write("     → 'Agree and access repository'")
        log.write("  3. [dim]export HF_TOKEN=hf_xxx[/]")
        log.write("     [dim]python download_models.py --hf-token $HF_TOKEN[/]")
        log.write("")
        log.write(
            "[dim]Alternative: 'Sprecher-Erkennung' auf [bold]Aus[/] setzen und neu starten.[/]"
        )

    def _gather_config(self, log: RichLog) -> PipelineConfig | None:
        audio_raw = self.query_one("#audio-path", Input).value.strip()
        if not audio_raw:
            log.write("[bold red]✗ Kein Audio-Pfad angegeben.[/]")
            self.query_one("#audio-path", Input).focus()
            return None
        audio_path = resolve_audio_path(audio_raw, PIPELINE_DIR)
        if not audio_path.exists():
            log.write(f"[bold red]✗ Datei nicht gefunden: {audio_path}[/]")
            self.query_one("#audio-path", Input).focus()
            return None

        return PipelineConfig(
            audio=str(audio_path),
            viz=str(self.query_one("#viz-type", Select).value or "dialogue"),
            language=str(self.query_one("#language", Select).value or "auto"),
            model=str(self.query_one("#model", Select).value or "large-v3-turbo"),
            diarize=str(self.query_one("#diarize", Select).value or "auto"),
            episode=self.query_one("#episode", Input).value.strip() or "EP 01",
            show_name=self.query_one("#show-name", Input).value.strip() or "Signal",
            skip_transcribe=self.query_one("#skip-transcribe", Checkbox).value,
            skip_meta=self.query_one("#skip-meta", Checkbox).value,
            skip_render=self.query_one("#skip-render", Checkbox).value,
            skip_upload=self.query_one("#skip-upload", Checkbox).value,
        )

    # ── UI Helpers ─────────────────────────────────────────────────────────

    def _set_pipeline_active(self, running: bool) -> None:
        self._pipeline_active = running
        btn = self.query_one("#run-btn", Button)
        if running:
            btn.label = "⏳  Läuft …"
            btn.add_class("-running")
            btn.disabled = True
        else:
            btn.label = "▶  Pipeline starten"
            btn.remove_class("-running")
            btn.disabled = False
            self.query_one("#time-label", Static).update("")

    def _advance(self, progress: float, label: str, step: int) -> None:
        pb = self.query_one("#progress-bar", ProgressBar)
        status = self.query_one("#step-label", Static)
        log = self.query_one(RichLog)
        if progress > self._current_progress:
            self._current_progress = progress
            pb.update(progress=progress)
            status.update(label)
        if step >= 2 and self._current_step < 2:
            self._current_step = step
            self._show_transcript_preview(log)
        elif step > self._current_step:
            self._current_step = step

    def _show_transcript_preview(self, log: RichLog) -> None:
        txt = PIPELINE_DIR / "output" / self._current_stem / f"{self._current_stem}.txt"
        if not txt.exists():
            return
        try:
            lines = [l for l in txt.read_text(encoding="utf-8").splitlines() if l.strip()]
            preview = lines[:20]
            log.write(f"\n[#22272f]{'─' * 60}[/]")
            log.write("[bold #5a6170]  Transkript-Vorschau[/]")
            log.write(f"[#22272f]{'─' * 60}[/]")
            for line in preview:
                if line.rstrip().endswith(":"):
                    log.write(f"  [bold #a878ff]{line}[/]")
                else:
                    log.write(f"  [dim]{line}[/]")
            if len(lines) > 20:
                log.write(f"  [dim]… {len(lines) - 20} weitere Zeilen[/]")
            log.write(f"[#22272f]{'─' * 60}[/]\n")
        except Exception:
            pass

    # ── Worker: Subprocess ─────────────────────────────────────────────────

    @work(thread=True)
    def _execute(self, cmd: list[str]) -> None:
        log = self.query_one(RichLog)
        status = self.query_one("#step-label", Static)
        pb = self.query_one("#progress-bar", ProgressBar)
        log_file_path = getattr(self, "_log_file_path", None)
        log_fh = None
        try:
            if log_file_path is not None:
                log_fh = log_file_path.open("w", encoding="utf-8", buffering=1)
                log_fh.write(f"# Pipeline-Run gestartet {datetime.now().isoformat()}\n")
                log_fh.write(f"# Command: {' '.join(cmd)}\n")
                log_fh.write("# " + "─" * 60 + "\n\n")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PIPELINE_DIR),
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                if log_fh is not None:
                    log_fh.write(line + "\n")
                self.call_from_thread(log.write, line)
                event = match_line(line, self._current_step)
                if event:
                    self.call_from_thread(
                        self._advance, event.progress, event.label, event.step,
                    )
            proc.wait()

            if proc.returncode == 0:
                self.call_from_thread(
                    log.write,
                    f"\n[dim]{'─' * 60}[/]\n[bold #b8e986]✓ Pipeline abgeschlossen.[/]",
                )
                self.call_from_thread(lambda: pb.update(progress=100))
                self.call_from_thread(status.update, "[green]✓ Fertig[/]")
                if log_fh is not None:
                    log_fh.write(f"\n# ✓ Pipeline abgeschlossen {datetime.now().isoformat()}\n")
            else:
                self.call_from_thread(
                    log.write,
                    f"\n[bold red]✗ Pipeline fehlgeschlagen (Exit {proc.returncode}).[/]",
                )
                self.call_from_thread(
                    status.update, f"[red]✗ Fehler (Exit {proc.returncode})[/]"
                )
                if log_fh is not None:
                    log_fh.write(f"\n# ✗ Pipeline fehlgeschlagen (Exit {proc.returncode}) "
                                 f"{datetime.now().isoformat()}\n")
        except Exception as exc:
            self.call_from_thread(log.write, f"\n[bold red]✗ Fehler: {exc}[/]")
            self.call_from_thread(status.update, "[red]✗ Fehler[/]")
            if log_fh is not None:
                log_fh.write(f"\n# ✗ TUI-Fehler: {exc}\n")
        finally:
            if log_fh is not None:
                log_fh.close()
            # State neu lesen — Pipeline hat ihn ja währenddessen geschrieben
            self.call_from_thread(self._refresh_resume_state_after_run)
            self.call_from_thread(self._set_pipeline_active, False)
