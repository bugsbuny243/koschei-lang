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
import socket
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
    def run_program(
        self, patch=None, program: str = READ_ONLY, serve_patch=None, persist_patch=None
    ) -> subprocess.CompletedProcess:
        real = mir_go_native.broker_runtime
        real_serve = mir_go_native.serve_runtime
        real_persist = mir_go_native.persist_runtime

        def patched_persist():
            source = real_persist()
            return persist_patch(source) if persist_patch else source

        def patched(grants, pins=None):
            source = real(grants, pins)
            return patch(source) if patch else source

        def patched_serve():
            source = real_serve()
            return serve_patch(source) if serve_patch else source

        with tempfile.TemporaryDirectory(prefix="koschei-grants-") as directory:
            base = Path(directory)
            (base / "root").mkdir()
            (base / "root" / "a.txt").write_text("merhaba", encoding="utf-8")
            (base / "main.ks").write_text(program, encoding="utf-8")
            binary = base / "app"
            with mock.patch.object(mir_go_native, "broker_runtime", patched), mock.patch.object(
                mir_go_native, "serve_runtime", patched_serve
            ), mock.patch.object(mir_go_native, "persist_runtime", patched_persist):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(cli_main(["build", str(base / "main.ks"), "-o", str(binary)]), 0, errors.getvalue())
            env = dict(os.environ, KS_TEST_SECRET=SECRET, KS_PUBLIC="public", PYTHONPATH=str(ROOT))
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

    # ---- scope pinning ---------------------------------------------------

    def test_token_created_but_never_used_runs(self) -> None:
        # Regression: grants once came only from token use, so a program that
        # narrowed the disk and never used the token was refused by the broker.
        program = 'fn main(caps: SystemCaps) {\n    let disk = caps.disk.allow_read_only("root")\n    println("done")\n}\n'
        result = self.run_program(program=program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "done\n")

    def test_literal_disk_prefix_is_pinned(self) -> None:
        def widen(source: str) -> str:
            patched = source.replace('_ksOpenDiskScope("scope", text)', '_ksOpenDiskScope("scope", text+"/..")')
            assert patched != source
            return patched

        result = self.run_program(widen)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("merhaba", result.stdout)

    def test_literal_env_name_is_pinned(self) -> None:
        program = 'fn main(caps: SystemCaps) {\n    let name = caps.env.allow("KS_PUBLIC")\n    println(name.get() or "missing")\n}\n'
        self.assertEqual(self.run_program(program=program).stdout, "public\n")

        def other(source: str) -> str:
            patched = source.replace('_ksAsk("env", env.name)', '_ksAsk("env", "KS_TEST_SECRET"+env.name[:0])')
            assert patched != source
            return patched

        result = self.run_program(other, program=program)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(SECRET, result.stdout + result.stderr)

    def test_computed_prefix_is_not_pinned(self) -> None:
        program = 'fn main(caps: SystemCaps) {\n    let where = "ro" + "ot"\n    let disk = caps.disk.allow_read_only(where)\n    println(disk.read("root/a.txt") or "fail")\n}\n'
        result = self.run_program(program=program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "merhaba\n")

    def test_literal_persist_path_is_pinned(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-pin-persist-") as directory:
            state = Path(directory)
            program = (
                "fn main(caps: SystemCaps) {\n"
                f'    let store = caps.persist.allow("{state}/data.txt", 64, 5000)\n'
                '    println(store.commit("kept"))\n'
                "}\n"
            )
            result = self.run_program(program=program)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((state / "data.txt").read_text(encoding="utf-8"), "kept")

            def elsewhere(source: str) -> str:
                old = '_ksAsk("persist_open", canonical,'
                assert old in source
                return source.replace(old, '_ksAsk("persist_open", canonical+".other",')

            result = self.run_program(program=program, persist_patch=elsewhere)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((state / "data.txt.other").exists())

    def test_literal_serve_bind_is_pinned(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        program = (
            "fn main(caps: SystemCaps) {\n"
            f'    let server = caps.serve.allow("127.0.0.1:{port}", 1, 1024, 1024, 100)\n'
            '    println("bound")\n'
            "}\n"
        )
        result = self.run_program(program=program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "bound\n")

        def other_port(source: str) -> str:
            old = '_ksAsk("serve_scope", text,'
            assert old in source
            return source.replace(old, '_ksAsk("serve_scope", text+"1",')

        result = self.run_program(program=program, serve_patch=other_port)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("bound", result.stdout)


class BrokerPinSourceTests(unittest.TestCase):
    def test_pins_are_rendered(self) -> None:
        source = broker_runtime(ALL_GRANTS, {"env": frozenset({"HOME"}), "scope": frozenset()})
        self.assertIn('case "env":\n\t\treturn text == "HOME"', source)
        self.assertIn('case "scope":\n\t\treturn false', source)
        with self.assertRaises(ValueError):
            broker_runtime(ALL_GRANTS, {"persist_load": frozenset()})


if __name__ == "__main__":
    unittest.main()
