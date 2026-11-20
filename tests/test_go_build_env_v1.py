"""`ks build` pins the Go toolchain's environment.

Before this, `ks build` passed the caller's environment to `go build`, so
GOFLAGS=-toolexec=<program> ran that program around every compiler step, and
GOPROXY/GOTOOLCHAIN could make the build reach the network. Generated
programs need only the standard library, so the build is pinned offline and
ignores GOFLAGS and the user's go env file.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from koschei.cli_entry import main as cli_main
from koschei.go_build_env_v1 import PINNED_GO_ENVIRONMENT, go_build_environment


class PinnedEnvironmentTests(unittest.TestCase):
    def test_pinned_values_override_the_caller(self) -> None:
        hostile = {"GOFLAGS": "-toolexec=/tmp/x", "GOPROXY": "https://evil.example",
                   "GOTOOLCHAIN": "go1.99.0", "GOENV": "/tmp/env", "GOWORK": "/tmp/go.work",
                   "CGO_ENABLED": "1", "KEEP_ME": "yes"}
        with mock.patch.dict(os.environ, hostile):
            environment = go_build_environment()
        for key, value in PINNED_GO_ENVIRONMENT.items():
            self.assertEqual(environment[key], value)
        self.assertEqual(environment["KEEP_ME"], "yes")


@unittest.skipUnless(shutil.which("go"), "Go toolchain unavailable")
class ToolexecInjectionTests(unittest.TestCase):
    def test_goflags_toolexec_does_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            marker = base / "pwned.txt"
            hook = base / "hook.sh"
            hook.write_text(f'#!/bin/sh\necho run >> "{marker}"\nexec "$@"\n', encoding="utf-8")
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
            source = base / "main.ks"
            source.write_text('fn main() {\n    println("hi")\n}\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"GOFLAGS": f"-toolexec={hook}"}), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = cli_main(["build", str(source), "-o", str(base / "app")])
            self.assertEqual(code, 0)
            self.assertFalse(marker.exists(), "GOFLAGS -toolexec ran during ks build")


if __name__ == "__main__":
    unittest.main()
