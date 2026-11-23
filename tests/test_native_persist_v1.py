"""PersistCaps and ServeCaps.exchange in native binaries, through the broker.

Each program runs under `ks run` and as a native binary; stdout, exit status
and the persisted bytes must match.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from koschei.cli_entry import main as cli_main

NATIVE = shutil.which("go") is not None and sys.platform.startswith("linux")


def ks_run(path: Path) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = cli_main(["run", str(path)])
    return code, out.getvalue()


def ks_build(path: Path, output: Path) -> None:
    errors = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(errors):
        code = cli_main(["build", str(path), "-o", str(output)])
    if code != 0:
        raise AssertionError(errors.getvalue())


@unittest.skipUnless(NATIVE, "native persistence needs Go on Linux")
class NativePersistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.base = Path(self._dir.name)
        (self.base / "state").mkdir()
        (self.base / "shared").mkdir()
        os.chmod(self.base / "shared", 0o777)
        (self.base / "a-file").write_text("x")
        os.symlink("/etc/hostname", self.base / "state" / "link.txt")

    def tearDown(self) -> None:
        self._dir.cleanup()

    def reset(self) -> None:
        for name in ("data.txt",):
            (self.base / "state" / name).unlink(missing_ok=True)
        (self.base / "shared" / "x.txt").unlink(missing_ok=True)

    def parity(self, body: str) -> str:
        source = self.base / "main.ks"
        source.write_text("fn main(caps: SystemCaps) {\n" + body + "}\n")
        self.reset()
        interpreted = ks_run(source)
        state = (self.base / "state" / "data.txt")
        interpreted_state = state.read_bytes() if state.exists() else None
        binary = self.base / "bin"
        binary.unlink(missing_ok=True)
        ks_build(source, binary)
        self.reset()
        completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
        native_state = state.read_bytes() if state.exists() else None
        self.assertEqual((completed.returncode, completed.stdout), interpreted)
        self.assertEqual(native_state, interpreted_state)
        if native_state is not None:
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        return completed.stdout

    def test_load_commit_and_budget(self) -> None:
        out = self.parity(
            f'    let store = caps.persist.allow("{self.base}/state/data.txt", 8, 5000)\n'
            "    println(store.load())\n"
            '    println(store.commit("123456789"))\n'
            '    println(store.commit("1234"))\n'
            "    println(store.load())\n"
        )
        self.assertEqual(
            out.splitlines(),
            [
                "KS3424: persistence state object does not exist",
                "KS3421: commit payload exceeds max_bytes",
                "unit",
                "1234",
            ],
        )

    def test_refusals_match_the_interpreter(self) -> None:
        out = self.parity(
            f'    let link = caps.persist.allow("{self.base}/state/link.txt", 64, 5000)\n'
            "    println(link.load())\n"
            '    println(link.commit("x"))\n'
            f'    let missing = caps.persist.allow("{self.base}/nope/x.txt", 64, 5000)\n'
            "    println(missing.load())\n"
            f'    let file_parent = caps.persist.allow("{self.base}/a-file/x.txt", 64, 5000)\n'
            '    println(file_parent.commit("x"))\n'
            f'    let shared = caps.persist.allow("{self.base}/shared/x.txt", 64, 5000)\n'
            '    println(shared.commit("x"))\n'
        )
        lines = out.splitlines()
        self.assertEqual(lines[0], "KS3420: persistence target may not be a symbolic link")
        self.assertEqual(lines[1], "KS3420: persistence target may not be a symbolic link")
        self.assertEqual(lines[2], "KS3424: persistence parent could not be anchored: [Errno 2] No such file or directory: 'nope'")
        self.assertEqual(lines[3], "KS3424: persistence parent could not be anchored: [Errno 20] Not a directory: 'a-file'")
        self.assertIn("sticky-bit", lines[4])
        self.assertFalse((self.base / "shared" / "x.txt").exists())

    def test_tokens_render_and_pass_through_functions(self) -> None:
        source = self.base / "main.ks"
        source.write_text(
            "fn save(store: PersistCaps, text: String) -> String or Error {\n"
            "    let done = store.commit(text) or return\n"
            "    return store.load()\n"
            "}\n\n"
            "fn main(caps: SystemCaps) {\n"
            "    println(caps.persist)\n"
            f'    let store = caps.persist.allow("{self.base}/state/data.txt", 64, 5000)\n'
            '    println(save(store, "kept") or "failed")\n'
            "}\n"
        )
        self.reset()
        interpreted = ks_run(source)
        binary = self.base / "bin"
        ks_build(source, binary)
        self.reset()
        completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
        self.assertEqual((completed.returncode, completed.stdout), interpreted)
        self.assertEqual(interpreted[1], "<PersistRoot>\nkept\n")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@unittest.skipUnless(NATIVE, "native exchange needs Go on Linux")
class NativeExchangeTests(unittest.TestCase):
    def run_exchange(self, command: list[str], port: int, request: bytes | None) -> tuple[int, str, bytes]:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        response = b""
        try:
            if request is not None:
                for _ in range(750):
                    try:
                        client = socket.create_connection(("127.0.0.1", port), timeout=1)
                        break
                    except OSError:
                        time.sleep(0.02)
                else:
                    raise AssertionError("listener never came up")
                with client:
                    client.sendall(request)
                    while chunk := client.recv(4096):
                        response += chunk
            stdout, _ = process.communicate(timeout=20)
        finally:
            if process.poll() is None:
                process.kill()
        return process.returncode, stdout, response

    def test_exchange_matches_the_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cases = {
                "ok": ("accepted", b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello"),
                "too_big_response": ("x" * 400, None),
                "bad_utf8": ("ok", b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n\xff\xfe"),
            }
            for label, (reply, request) in cases.items():
                with self.subTest(label):
                    results = []
                    for runner in ("interpreter", "native"):
                        # A fresh port per run: the previous run's closed
                        # connection may still hold the old one in TIME_WAIT.
                        port = _free_port()
                        source = base / f"{label}-{runner}.ks"
                        source.write_text(
                            "fn main(caps: SystemCaps) {\n"
                            f'    let server = caps.serve.allow("127.0.0.1:{port}", 1, 4096, 256, 10000)\n'
                            f'    println(server.exchange("{reply}"))\n'
                            "}\n"
                        )
                        if runner == "interpreter":
                            command = [sys.executable, "-m", "koschei", "run", str(source)]
                        else:
                            binary = base / f"{label}.bin"
                            ks_build(source, binary)
                            command = [str(binary)]
                        results.append(self.run_exchange(command, port, request))
                    self.assertEqual(results[1], results[0])

    def test_production_reference_builds_with_the_confined_backend(self) -> None:
        from koschei.workspace import load_workspace
        from koschei.workspace_execution import _analyze_workspace_package

        root = Path(__file__).resolve().parent.parent / "examples" / "production_reference_v1"
        source, _, _ = _analyze_workspace_package(load_workspace(root), "http_ingress")
        self.assertIn("_ksBrokerEntry", source)
        self.assertIn("_ksPersistCommit", source)
        self.assertIn("_ksServeExchange", source)


if __name__ == "__main__":
    unittest.main()
