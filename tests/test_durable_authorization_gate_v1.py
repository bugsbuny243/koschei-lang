"""Canonical validation bridge for the durable authorization acceptance suite.

Koschei's release gate intentionally uses ``unittest discover`` as its first
repository-wide test step.  The durable authorization tests are pytest-style
functions, so unittest discovery imports that module but does not execute those
functions.  This additive bridge makes the existing canonical gate execute that
security suite without changing the release gate's global test runner.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
DURABLE_SUITE = "tests/test_durable_authorization_store_v1.py"


class DurableAuthorizationCanonicalGateV1(unittest.TestCase):
    """Require the durable replay/revocation suite inside canonical validation."""

    def test_durable_authorization_pytest_suite(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", DURABLE_SUITE],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(
                "durable authorization acceptance suite failed under canonical "
                f"validation (exit={proc.returncode}):\n{proc.stdout}"
            )


if __name__ == "__main__":
    unittest.main()
