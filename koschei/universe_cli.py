"""Launch the Koschei Universe for a real Koschei project."""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

from .universe_project_provider_v1 import build_project_universe_v1
from .universe_web_v1 import serve_universe_v1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ks-universe", description="Open a real Koschei project in Universe Mode")
    parser.add_argument("source", help="Root .ks source file")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback address only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.source).resolve()
    if source.suffix != ".ks" or not source.is_file():
        raise SystemExit(f"KOSCHEI UNIVERSE ERROR: real .ks source required: {source}")

    def provider():
        state = build_project_universe_v1(source)
        return state.projection, state.live

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        def opener() -> None:
            time.sleep(0.35)
            webbrowser.open(url)
        threading.Thread(target=opener, daemon=True).start()

    print(f"KOSCHEI UNIVERSE: {url}")
    print(f"PROJECT: {source}")
    print("MODE: canonical project state / read-only / authority-free")
    serve_universe_v1(provider, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
