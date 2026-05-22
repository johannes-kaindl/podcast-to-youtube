#!/usr/bin/env python3
"""
YouTube OAuth einmalig autorisieren.
Muss direkt im Terminal laufen (nicht via Claude-Code-!-Befehl),
damit der Browser geöffnet werden kann.

Usage:
  source .venv/bin/activate
  python auth_youtube.py
"""
import os
import pickle
import sys
from pathlib import Path

SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".youtube_token.pickle")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("FEHLER: google-auth-oauthlib nicht installiert.")
        print("  pip install google-auth-oauthlib")
        sys.exit(1)

    if os.path.exists(TOKEN_FILE):
        print(f"Token existiert bereits: {TOKEN_FILE}")
        print("Zum Neu-Authorisieren: rm .youtube_token.pickle && python auth_youtube.py")
        sys.exit(0)

    if not os.path.exists(SECRETS_FILE):
        print(f"FEHLER: {SECRETS_FILE} nicht gefunden.")
        sys.exit(1)

    print("YouTube OAuth-Autorisierung...")
    print("→ Browser öffnet sich gleich.")
    print("→ Mit dem Google-Konto einloggen, das Zugriff auf den YouTube-Kanal hat.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

    print()
    print(f"✓ Token gespeichert: {TOKEN_FILE}")
    print("  Ab jetzt läuft upload_youtube.py und pipeline.py ohne Browser-Popup.")


if __name__ == "__main__":
    main()
