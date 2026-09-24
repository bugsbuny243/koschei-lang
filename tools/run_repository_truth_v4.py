#!/usr/bin/env python3
"""Run the repository truth gate against the canonical MIR version.

The historical in-memory MIR-v3 substitution has been retired. `verify.sh`
now imports the canonical MIR version directly, so this entry point is only a
stable automation wrapper around the repository-owned truth script.
"""
from __future__ import annotations

from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY = REPO_ROOT / "verify.sh"


def main() -> int:
    if not VERIFY.is_file():
        print("repository-truth-v4: verify.sh is missing")
        return 2
    completed = subprocess.run(
        ["bash", str(VERIFY)],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
