"""Serve the Koschei Pi sandbox bridge on localhost:3000.

Development helper only. This server intentionally binds to loopback and serves
static files from distribution/pi-sandbox-web. It is not a production server.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "distribution" / "pi-sandbox-web"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("sandbox server must bind to loopback only")
    if not WEB_ROOT.is_dir():
        parser.error(f"sandbox web root is missing: {WEB_ROOT}")
    if not (1 <= args.port <= 65535):
        parser.error("port must be between 1 and 65535")

    handler = partial(SimpleHTTPRequestHandler, directory=str(WEB_ROOT))
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"KOSCHEI PI SANDBOX: http://{args.host}:{args.port}")
        print("mode: development only; Ctrl-C to stop")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nKOSCHEI PI SANDBOX: stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
