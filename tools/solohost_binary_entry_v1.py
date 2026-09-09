"""Customer-distribution entry point for the sealed Koschei CLI binary.

This wrapper deliberately contains no Pi payment logic and no language semantics.
It exists only to give the owner-controlled binary packager a narrow executable
entry point that delegates to the canonical Koschei CLI.
"""
from __future__ import annotations

from koschei.cli_entry import main


if __name__ == "__main__":
    raise SystemExit(main())
