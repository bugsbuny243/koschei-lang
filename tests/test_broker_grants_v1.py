"""The broker serves only the authority the compiled program uses.

formal/tla/BrokerConfinement.tla found that a worker able to send arbitrary
frames (a compromised worker: seccomp still holds) could ask the broker for a
writable scope or an environment variable even when the program had neither.
These tests simulate such a worker by patching the worker-side runtime after
the grants were computed from the program, and check the broker refuses.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from koschei import mir_go_native
from koschei.cli_entry import main as cli_main
from koschei.native_broker_v1 import ALL_GRANTS, broker_runtime

ROOT = Path(__file__).resolve().parent.parent
SUPPORTED = shutil.which("go") is not None and sys.platform == "linux" and platform.machine() in {"x86_64", "AMD64"}

READ_ONLY = """
fn main(caps: SystemCaps) {
    let disk = caps.disk.allow_read_only("root")
    println(disk.read("root/a.txt"))
}
"""

SECRET = "ks-grant-test-secret"


def _escalate_scope(source: str) -> str:
    patched = source.replace('_ksOpenDiskScope("scope", text)', '_ksOpenDiskScope("scope_rw", text)')
    assert patched != source
    return patched


def _ask_env(source: str) -> str:
    anchor = "\ttext := _ksDiskPath(path)\n\tok, answer := _ksAsk(\"read\""
    assert anchor in source
    leak = '\tif found, leaked := _ksAsk("env", "KS_TEST_SECRET"); found {\n\t\tprintln("LEAK " + leaked[0])\n\t}\n'
    return source.replace(anchor, leak + anchor, 1)


class BrokerGrantSourceTests(unittest.TestCase):
    def test_grants_are_rendered(self) -> None:
        none = broker_runtime(frozenset())
        self.assertIn("_ksGrantDiskRead  = false", none)
        self.assertIn("_ksGrantDiskWrite = false", none)
        self.assertIn("_ksGrantEnv       = false", none)
        full = broker_runtime(ALL_GRANTS)
        self.assertIn("_ksGrantDiskWrite = true", full)
        with self.assertRaises(ValueError):
            broker_runtime(frozenset({"net"}))


@unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
class BrokerGrantRuntimeTests(unittest.TestCase):
    def run_program(self, patch=None) -> subprocess.CompletedProcess:
        real = mir_go_native.broker_runtime

        def patched(grants):
            source = real(grants)
            return patch(source) if patch else source

        with tempfile.TemporaryDirectory(prefix="koschei-grants-") as directory:
            base = Path(directory)
            (base / "root").mkdir()
            (base / "root" / "a.txt").write_text("merhaba", encoding="utf-8")
            (base / "main.ks").write_text(READ_ONLY, encoding="utf-8")
            binary = base / "app"
            with mock.patch.object(mir_go_native, "broker_runtime", patched):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(cli_main(["build", str(base / "main.ks"), "-o", str(binary)]), 0, errors.getvalue())
            env = dict(os.environ, KS_TEST_SECRET=SECRET, PYTHONPATH=str(ROOT))
            return subprocess.run([str(binary)], cwd=base, env=env, capture_output=True, text=True, timeout=60, check=False)

    def test_honest_worker_runs(self) -> None:
        result = self.run_program()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "merhaba\n")

    def test_read_only_program_cannot_get_a_writable_scope(self) -> None:
        result = self.run_program(_escalate_scope)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("merhaba", result.stdout)

    def test_program_without_env_cannot_read_the_environment(self) -> None:
        result = self.run_program(_ask_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(SECRET, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
