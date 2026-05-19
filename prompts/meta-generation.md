---
purpose: User-Prompt-Template für YouTube-Metadaten-Generierung
last-tuned: 2026-05-13
notes: |
  Wird zur Laufzeit mit den konkreten Werten gefüllt und als `user`-
  Nachricht an MLX gesendet (System-Role kommt aus meta-system.md).

  Placeholder:
    {show_name}      — Podcast-Serienname (z.B. "Signal")
    {episode}        — Episodennummer/-titel
    {duration_min}   — Audiodauer in Minuten (float, mit .0f formatiert)
    {language_name}  — voller Sprachname (z.B. "English", "Deutsch")
    {language_code}  — ISO-Code (de/en/...) für meta["language"]
    {transcript}     — vollständiger Transkript-Text (max 60k Zeichen)

  JSON-Schema des Outputs wird hier direkt im Prompt vorgegeben (Few-Shot).
  Bei Schema-Änderungen Loader in generate_meta.py prüfen
  (parse_json_response, format_description_with_chapters).
---

Erstelle vollständige YouTube-Metadaten für dieses Podcast-Transkript.

Podcast-Name: {show_name}
Episodennummer: {episode}
Audiodauer: {duration_min:.0f} Minuten
Sprache: {language_name} — alle generierten Texte müssen in dieser Sprache sein.

TRANSKRIPT:
{transcript}

Gib NUR dieses JSON-Objekt zurück (keine anderen Zeichen davor oder dahinter):
{{
  "title": "...",
  "show_name": "...",
  "description_hook": "...",
  "description_full": "...",
  "chapters": [{{"time": "00:00", "title": "Intro"}}, {{"time": "MM:SS", "title": "..."}}],
  "tags": ["...", "..."],
  "hashtags": ["#...", "#..."],
  "category_id": "27",
  "language": "{language_code}"
}}
