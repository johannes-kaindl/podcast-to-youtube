#!/usr/bin/env python3
"""WebGUI entry-point.

Usage:
  python webgui.py             # opens browser at http://localhost:8765
  python webgui.py --port 9000 # custom port
  python webgui.py --no-open   # don't open browser
"""
import argparse
import threading
import time
import webbrowser

import uvicorn


def _open_browser_after_delay(url: str, delay: float = 1.0) -> None:
    time.sleep(delay)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper-Pipeline WebGUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--reload", action="store_true", help="Dev mode: reload on file change")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        threading.Thread(
            target=_open_browser_after_delay, args=(url,), daemon=True,
        ).start()

    print(f"\n  Whisper-Pipeline WebGUI  ->  {url}\n")
    uvicorn.run(
        "webgui.app:app",
        host=args.host, port=args.port,
        reload=args.reload, log_level="info",
    )


if __name__ == "__main__":
    main()
