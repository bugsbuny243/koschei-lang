from __future__ import annotations

import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
