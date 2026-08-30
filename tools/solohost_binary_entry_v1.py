"""Customer-distribution entry point for the sealed Koschei CLI binary.

This wrapper deliberately contains no Pi payment logic and no language semantics.
It exists only to give the owner-controlled binary packager a narrow executable
entry point that delegates to the canonical Koschei CLI.
"""
from __future__ import annotations

import sys

from koschei.cli_entry import main


def _force_utf8_stdio() -> None:
    """Keep sealed CLI diagnostics portable across minimal/non-UTF-8 Linux locales."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (LookupError, OSError, ValueError):
            # Never block compiler startup just because a host stream cannot
            # be reconfigured; normal Python stream behaviour remains intact.
            pass


if __name__ == "__main__":
    _force_utf8_stdio()
    raise SystemExit(main())
