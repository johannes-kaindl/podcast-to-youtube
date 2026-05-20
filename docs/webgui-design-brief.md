# Whisper-Pipeline · WebGUI — Design-Brief

**Status:** Brief für UI-Mockup-Erstellung. Tech-Architektur ist separat festgelegt (FastAPI + Jinja2 + HTMX, server-rendered HTML, kein SPA).

**Ziel des Briefs:** HTML-Mockups + CSS, die später als Templates in eine FastAPI/Jinja2-Anwendung übernommen werden. Lieferung als statische `.html`-Dateien (eine pro Screen) plus eine zentrale `style.css`. Keine React/Vue/Svelte-Komponenten, kein Build-Step.

---

## 1 · Projekt-Kontext

**Whisper-Pipeline** ist ein lokales Tool, das einen Podcast-Audio-File (`.m4a` / `.mp3` / `.wav`) in vier Phasen zu einem fertigen YouTube-Video verarbeitet:

1. **Transkription** — WhisperX (lokal) erzeugt Word-Level-Timecodes, Speaker-Labels, .srt, .txt
2. **Metadaten** — lokales LLM (MLX) generiert YouTube-Titel, Beschreibung, Tags, Kapitel
3. **Render** — Remotion (Node.js) erzeugt eine MP4 mit Visualizer (Dialogue oder Monologue)
4. **Upload** — YouTube Data API v3, Video landet als Private im Kanal

Alles läuft lokal. Die WebGUI ist das primäre Interface, das die heutige Textual-TUI ablöst.

---

## 2 · Nutzer:in und Nutzungs-Kontext

- **Single-User**, eine Person produziert ihre eigenen Podcasts
- **Localhost** im Browser am Mac (kein Remote, keine Auth)
- **Sessions** dauern Minuten bis ~30 Min (Transkription + Render brauchen ihre Zeit)
- **Persona:** technisch versiert (kennt CLI), legt Wert auf Übersicht und Vertrauen ("habe ich noch Kontrolle über den Upload?"), nicht auf Klick-Effizienz

---

## 3 · Tech-Constraints fürs Mockup

- **Server-rendered HTML.** Jinja2-Templates später; jetzt einfach `.html`-Dateien.
- **HTMX-tauglich.** Interaktive Updates werden via `hx-get`, `hx-post`, `hx-swap`-Attribute auf bestehende Elemente nachgerüstet. Das Mockup darf zeigen, wie Bereiche ausgetauscht werden (z.B. „Status-Banner ändert sich"), muss aber kein JS-Logik enthalten.
- **SSE für Live-Log.** Stdout-Zeilen einer laufenden Pipeline streamen ins Log-Panel. Im Mockup: einfach ein Bereich mit Codeblock-Look, der so aussieht, als würden Zeilen nachfließen.
- **Vendored Assets.** Keine CDN-Links, kein Tailwind-CDN. Falls Tailwind: Build-Step okay, aber Vorzug für **vanilla CSS** mit Custom Properties (`--color-…`).
- **Kein Komponenten-System.** Wiederholte Bauteile sind Klassen-basiert (`.run-card`, `.phase-indicator`, …), nicht Web-Components.

---

## 4 · Screens

### 4.1 — `index.html` (Start / Konfiguration)

Das ist der Landing-Screen. User landet hier, gibt Audio-Pfad ein, wählt Optionen, startet die Pipeline.

**Inhaltsbereiche:**

- **Header** — Titel "Whisper-Pipeline", evtl. Subtitle "Transkription · Meta · Render · Upload"
- **Audio-Auswahl** — Pfad-Input (Drag-and-Drop-Zone wäre nice-to-have), Anzeige des erkannten Stems
- **Resume-Banner** *(bedingt — nur wenn `output/<stem>/run-state.json` existiert)* — zeigt den Status eines früheren Runs als Glyph-Reihe (✓ Transkription · ⟳ Metadaten · ✗ Render · · Upload), mit Hint "Skip-Boxen sind voreingestellt"
- **Konfiguration** — Formular:
  - Visualizer (Select: Dialogue / Monologue)
  - Sprache (Auto / de / en)
  - Modell (large-v3-turbo, large-v3, large-v2, medium, small, base, tiny)
  - Sprecher-Erkennung (Auto / 2 / 3 / 4 / 5 / Aus)
  - Episode (Text)
  - Kanal/Serienname (Text)
  - Skip-Phasen (4 Checkboxen)
- **Run-Trigger** — primärer Button "▶ Pipeline starten" (Ctrl+R-Hint)
- **Sekundär-Link** — "Vergangene Runs ansehen" → `/runs`

### 4.2 — `run_detail.html` (laufender oder fertiger Run)

Wo der User die meiste Zeit verbringt. Während Pipeline läuft: Live-Updates. Nach Fertigstellung: Übersicht + Upload-Button.

**Inhaltsbereiche:**

- **Run-Header** — Stem, Audio-Pfad, Start-Zeitpunkt, Gesamtdauer (live tickend)
- **Phase-Indikator-Strip** — 4 Phasen horizontal: Transkription · Metadaten · Render · Upload. Jede mit Status (pending · running · done · aborted · skipped) und je nach Status anderer Optik (z.B. running = animierte Border / Puls; done = grün; aborted = rot)
- **Progress-Bar** — eine Gesamtleiste, ergänzt durch die Phase-Indikatoren oben
- **Live-Log-Panel** — Monospaced Codeblock, scrollt mit, neue Zeilen unten dran. Soll wie ein Terminal aussehen, aber lesbar (genug Padding, gut gewähltes Mono-Font)
- **Transkript-Preview** *(erscheint nach Phase 1)* — ein paar Zeilen mit Speaker-Doppelpunkt-Format ("Alice: …", "Bob: …") als Lesbarkeits-Check
- **MP4-Preview** *(erscheint nach Phase 3)* — `<video controls>` mit dem fertig gerenderten Clip
- **YouTube-Metadaten-Card** *(erscheint nach Phase 2)* — Card mit Titel, Beschreibung-Preview (ggf. truncated), Tags als Chips, Kapitel-Liste (Timestamp + Label). Read-only im V1.
- **Upload-Trigger** *(erscheint nach Phase 3 wenn nicht skipped)* — großer Button "↑ Auf YouTube hochladen" mit Privacy-Wahl daneben (Private / Unlisted). User muss aktiv klicken.
- **Upload-Done-Card** *(nach Phase 4)* — YouTube-URL, "Im Browser öffnen"-Link

### 4.3 — `runs.html` (Run-Historie / Output-Browser)

Liste aller verarbeiteten Audios. Klick auf Run-Card → `run_detail.html`.

**Inhaltsbereiche:**

- **Header** — "Vergangene Runs", "Neuer Run starten"-Link zurück zu `/`
- **Filter-/Sortier-Bar** *(nice-to-have)* — z.B. nach Datum, Status (alle / fertig / abgebrochen / unfertig)
- **Run-Card-Liste** — pro Run eine Card:
  - Stem als Titel
  - Datum/Zeit
  - Phase-Indikator-Strip (kompakte Variante)
  - MP4-Thumbnail falls vorhanden (am besten ein Standbild aus dem MP4; im Mockup Placeholder)
  - YouTube-URL falls hochgeladen
  - Hover-State erkennbar

---

## 5 · Komponenten (Mockup-Kernstücke)

### 5.1 — Phase-Indikator-Strip

Vier Phasen nebeneinander, je ein Glyph + Label + Status-Farbe. Verwendungen:
- **Voll-Variante** in `run_detail.html`: groß, mit Animation für `running`, Zeit-Info pro Phase
- **Kompakt-Variante** in `runs.html` (Run-Card): klein, nur Glyph + Farbe

Status-Mapping:
- `pending` — ○ (grau, leicht ausgegraut)
- `running` — ⟳ (Akzentfarbe, pulsierend/rotierend)
- `done` — ✓ (Erfolgsfarbe)
- `aborted` — ✗ (Fehlerfarbe)
- `skipped` — · (gedämpft, kleiner)

### 5.2 — Live-Log-Panel

Monospaced, dunkler Hintergrund, leicht erhöhter Kontrast. Format jeder Zeile: optionales Timestamp-Prefix, dann Text. Soll bei langer Output-Länge sauber scrollen — auto-scroll-to-bottom, mit "User-scrolled-up → pause auto-scroll"-Verhalten (kann später im JS gelöst werden; im Mockup einfach Mono-Block).

Hervorhebung optional: SUCCESS-Marker als grüner Strich am Zeilenanfang, WARN/ERROR als gelbe/rote.

### 5.3 — Run-Card

In `runs.html`. Eine ganze Karte, klickbar als Link. Inhalte siehe 4.3.

### 5.4 — Resume-Banner

In `index.html` über dem Formular. Drei Varianten:
- **Aborted/Unterbrochen** — gelb-warm, "Letzter Run: [Phase] abgebrochen. Skip-Boxen für fertige Phasen vorab angehakt."
- **Komplett** — grün-positiv, "Letzter Run komplett. Für Neu-Render: Skip-Render entfernen."
- **In-Progress (extern beendet)** — neutral, "Vorhandener Run gefunden."

### 5.5 — Form-Felder

Standard-Inputs (Text, Select, Checkbox). Aber bitte konsistent gestylet, nicht Browser-Default. Selects sollten zu Selects auf dem System passen (keine schweren Custom-Dropdowns).

---

## 6 · Stil-Richtung (offen — bitte Vorschläge)

**Vorgaben:**
- **Dark Mode bevorzugt** (User arbeitet abends an Podcasts), aber Light Mode sollte mit-funktionieren (CSS Custom Properties + `prefers-color-scheme`)
- **Kontrast hoch genug** für längere Lesezeit
- **Akzentfarbe** sollte zu „Audio/Signal" passen — denkbar: warmes Violett (#a878ff war in der TUI), tief-Cyan, warmes Orange. Genau die richtige Wahl ist Designentscheidung
- **Typografie** — gute UI-Sans (Inter, IBM Plex Sans, ähnlich) für Text, gute Mono (IBM Plex Mono, JetBrains Mono, oder System-Mono) für Log und Code

**Inspirationen:**
- Linear, Vercel-Dashboard, Cursor's UI — clean, dunkel, hochwertig
- TUI-Charakter erhalten: an Stellen wie Live-Log und Phase-Indikatoren soll der „Terminal-Spirit" durchscheinen
- KEINE Bling-Animationen, KEINE überladenen Gradient-Hintergründe

---

## 7 · Interaktive Zustände (im Mockup zumindest skizziert)

- **Audio-Input leer vs. valider Pfad** (validation-feedback)
- **Pipeline läuft** (Run-Button disabled, Phase-Indikator running)
- **Pipeline fertig** (Upload-Button erscheint)
- **Pipeline abgebrochen** (Fehler-Bereich mit letzten 10 Log-Zeilen)
- **Resume-Banner** in den drei Varianten oben
- **Empty State** in `runs.html` falls noch keine Runs existieren

---

## 8 · Output-Erwartung

Liefere bitte:

1. Drei `.html`-Dateien — `index.html`, `run_detail.html`, `runs.html` — als statische Mockups (mit `<head>`, eingebundenem CSS, gerne mit Dummy-Daten)
2. **Eine** `style.css` (oder ggf. zwei: `tokens.css` + `style.css`), die alle drei Mockups bedient
3. Für `run_detail.html`: bitte alle interaktiven Zustände sichtbar machen — entweder durch Inline-Variants im selben File oder durch drei separate Versionen (z.B. `run_detail--running.html`, `run_detail--done.html`, `run_detail--aborted.html`)
4. Eine kurze README, die die Design-Tokens (Farben, Typo-Größen) beschreibt, damit die Werte in der späteren Theme-Anpassung wiedergefunden werden können

**Aspekt-Hinweis:** Mockups sollen für Desktop-Browser-Fenster (≥ 1200px breit) ausgelegt sein. Mobile/Tablet ist später; im V1 nicht im Scope.

---

## 9 · Was NICHT im Scope ist (Phase 2)

Diese Features kommen erst in einer späteren Spec — nicht jetzt mit-designen:

- Transkript-Editor (in-place Korrektur, Re-Render-Trigger)
- Job-Queue / Multi-Audio-Verarbeitung
- Auth, Multi-User, Remote-Zugriff
- Tag-/Kategorien-Verwaltung

---

**Wenn etwas im Brief unklar ist, frag bitte zurück — lieber eine Nachfrage als eine Vermutung.**
