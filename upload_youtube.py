#!/usr/bin/env python3
"""
Video zu YouTube hochladen (als Private).
OAuth-Token wird beim ersten Lauf interaktiv erstellt und dann gecacht.

Setup:
  1. Google Cloud Console: Projekt + YouTube Data API v3 aktivieren
  2. OAuth 2.0 Credentials (Desktop App) herunterladen als client_secrets.json
  3. Datei in diesen Ordner legen
  4. Ersten Lauf im Terminal ausführen (öffnet Browser für OAuth)

Usage:
  python upload_youtube.py video.mp4 --meta meta.youtube-meta.json
  python upload_youtube.py video.mp4 --title "Titel" --description "Beschreibung"
"""
import argparse
import json
import os
import pickle
import sys
from pathlib import Path

SECRETS_FILE = os.path.join(os.path.dirname(__file__), "client_secrets.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".youtube_token.pickle")
PLAYLISTS_FILE = os.path.join(os.path.dirname(__file__), "playlists.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def load_playlist_mapping() -> dict[str, str]:
    """Lädt das Playlist-Mapping. Schlüssel sind show_name (oder 'default'
    als Fallback für nicht-gematchte Shows). Kommentar-Keys (Unterstrich-
    Präfix) und leere Strings werden gefiltert."""
    if not os.path.exists(PLAYLISTS_FILE):
        return {}
    with open(PLAYLISTS_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_") and v}


def resolve_playlist_id(show_name: str | None, explicit_id: str | None) -> str | None:
    """Auflösungs-Reihenfolge: explizite --playlist-id > show_name-Match >
    'default'-Key > None. Damit landen alle Uploads ohne show_name-spezifischen
    Eintrag automatisch in der default-Playlist."""
    if explicit_id:
        return explicit_id
    mapping = load_playlist_mapping()
    if show_name and show_name in mapping:
        return mapping[show_name]
    return mapping.get("default")


def add_to_playlist(youtube, video_id: str, playlist_id: str) -> bool:
    """Hängt Video an Playlist. Return True bei Erfolg, False bei Fehler
    (loggt aber den Fehler — Upload selbst war erfolgreich, Playlist ist
    nice-to-have und soll den Workflow nicht crashen)."""
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                }
            }
        ).execute()
        return True
    except Exception as e:
        print(f"  ⚠ Playlist-Assignment fehlgeschlagen: {e}")
        return False


def get_credentials():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        import google.auth
    except ImportError:
        print("FEHLER: Google-Bibliotheken fehlen.")
        print("Installieren: pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        from google.auth.exceptions import RefreshError
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Refresh token revoked or expired — drop it and re-authorize.
                print("OAuth-Token abgelaufen oder widerrufen — neue Anmeldung nötig.")
                creds = None
        if not creds or not creds.valid:
            if not os.path.exists(SECRETS_FILE):
                print(f"\nFEHLER: {SECRETS_FILE} nicht gefunden.")
                print("\nSetup-Anleitung:")
                print("1. https://console.cloud.google.com/ → Neues Projekt")
                print("2. APIs & Services → YouTube Data API v3 aktivieren")
                print("3. Credentials → OAuth 2.0 Client ID (Desktop App)")
                print("4. JSON herunterladen und als client_secrets.json in diesen Ordner")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
        print("OAuth-Token gespeichert.")

    return creds


def upload(video_path: str, title: str, description: str, tags: list[str],
           category_id: str = "27", language: str = "de",
           privacy: str = "private", publish_at: str | None = None,
           thumbnail_path: str | None = None,
           show_name: str | None = None,
           playlist_id: str | None = None) -> dict:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("FEHLER: google-api-python-client nicht installiert.")
        sys.exit(1)

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    status_body = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,  # Audio = NotebookLM (Google) — Transparenz-Flag
    }
    if publish_at and privacy == "private":
        # Geplante Veröffentlichung — ändert Status auf "scheduled"
        status_body["publishAt"] = publish_at

    snippet = {
        "title": title[:100],  # YouTube-Limit
        "description": description[:5000],
        "tags": tags[:500],  # Tag-Zeichenlimit-Puffer
        "categoryId": category_id,
        "defaultLanguage": language,
        "defaultAudioLanguage": language,
    }

    file_size = os.path.getsize(video_path)
    print(f"Uploading: {os.path.basename(video_path)} ({file_size / 1024**2:.1f} MB)")

    request = youtube.videos().insert(
        part="snippet,status",
        body={"snippet": snippet, "status": status_body},
        media_body=MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload: {pct}%", end="\r")

    video_id = response["id"]
    print(f"\n✓ Upload abgeschlossen: https://www.youtube.com/watch?v={video_id}")
    print(f"  Status: {privacy} (in Studio auf Öffentlich setzen zum Veröffentlichen)")

    # Thumbnail hochladen
    if thumbnail_path and os.path.exists(thumbnail_path):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        ).execute()
        print(f"  Thumbnail: {thumbnail_path}")

    # Playlist-Auto-Assignment: explizite --playlist-id > show_name-Match > default.
    effective_playlist_id = resolve_playlist_id(show_name, playlist_id)
    if effective_playlist_id:
        if add_to_playlist(youtube, video_id, effective_playlist_id):
            print(f"  Playlist: {effective_playlist_id}")

    return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}


def main():
    parser = argparse.ArgumentParser(description="YouTube-Upload")
    parser.add_argument("video", help="MP4-Videodatei")
    parser.add_argument("--meta", help="JSON-Metadatendatei (aus generate_meta.py)")
    parser.add_argument("--title", help="Episodentitel (überschreibt --meta)")
    parser.add_argument("--description", help="Beschreibung (überschreibt --meta)")
    parser.add_argument("--tags", nargs="+", help="Tags (überschreibt --meta)")
    parser.add_argument("--privacy", default="private",
                        choices=["private", "unlisted", "public"])
    parser.add_argument("--publish-at", help="ISO-8601 Datum (nur bei --privacy private)")
    parser.add_argument("--thumbnail", help="Thumbnail-Bilddatei")
    parser.add_argument("--playlist-id", help="YouTube-Playlist-ID (überschreibt show_name-Mapping)")
    args = parser.parse_args()

    meta = {}
    if args.meta and os.path.exists(args.meta):
        with open(args.meta, encoding="utf-8") as f:
            meta = json.load(f)

    title = args.title or meta.get("title", Path(args.video).stem)
    description = args.description or meta.get("description", "")
    tags = args.tags or meta.get("tags", [])
    category_id = meta.get("category_id", "27")
    language = meta.get("language", "de")
    show_name = meta.get("show_name")

    result = upload(
        video_path=args.video,
        title=title,
        description=description,
        tags=tags,
        category_id=category_id,
        language=language,
        privacy=args.privacy,
        publish_at=args.publish_at,
        thumbnail_path=args.thumbnail,
        show_name=show_name,
        playlist_id=args.playlist_id,
    )
    print(f"\nVideo-ID: {result['video_id']}")
    print(f"URL:      {result['url']}")


if __name__ == "__main__":
    main()
