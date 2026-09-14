#!/usr/bin/env python3
"""Run the historical repository truth gate against the canonical MIR version.

`verify.sh` still contains one legacy MIR-v3 assertion. Replacing the entire
large shell gate for a one-line migration would create needless review risk, so
this bridge performs one exact, fail-closed substitution in memory and executes
the otherwise byte-identical gate from the repository root.

This bridge is transitional. Once `verify.sh` is migrated to the canonical MIR
version directly, this tool should be deleted rather than becoming a second
release authority.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from koschei.mir import MIR_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY = REPO_ROOT / "verify.sh"
LEGACY_ASSERTION = 'assert mir.get("version") == 3'


def patched_verify_text() -> str:
    text = VERIFY.read_text(encoding="utf-8")
    count = text.count(LEGACY_ASSERTION)
    if count != 1:
        raise RuntimeError(
            "repository truth bridge expected exactly one legacy MIR-v3 assertion; "
            f"found {count}. Migrate or review verify.sh explicitly."
        )
    canonical = f'assert mir.get("version") == {MIR_VERSION}'
    return text.replace(LEGACY_ASSERTION, canonical, 1)


def main() -> int:
    try:
        script = patched_verify_text()
    except (OSError, RuntimeError) as error:
        print(f"repository-truth-v4: {error}", file=sys.stderr)
        return 2

    completed = subprocess.run(
        ["bash", "-s"],
        cwd=REPO_ROOT,
        input=script.encode("utf-8"),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
