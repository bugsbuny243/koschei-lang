"""The example applications run, compile and agree with their native binaries."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from koschei.cli_entry import main as cli_main

ROOT = Path(__file__).resolve().parent.parent / "examples" / "apps"
GO = shutil.which("go")


def digest(text: str) -> str:
    return "sha3-256:" + hashlib.sha3_256(text.encode()).hexdigest()


def secure_digest(context: str, parts: list[str]) -> str:
    encoded = f"koschei.secure.digest/v1\n{len(context)}:{context}"
    for part in parts:
        encoded += f"\n{len(part)}:{part}"
    return digest(encoded)


A, B, C = digest("app-1.0"), digest("app-1.1"), digest("lib-0.9")
GATE = (
    f"advisory CVE-2026-0001 {A}\nsupport {A} vendor 21000\nsupport {B} vendor 21000\n"
    f"support {C} oldvendor 20000\nbackport {C} distro 21500\n"
    f"check {A}\ncheck {B}\ncheck {C}\ncheck 8.1.2\nnonsense\n"
)
GATE_OUTPUT = (
    f"REFUSE {A} xandar=known-vulnerable morag=within-support\n"
    f"SHIP {B} xandar=no-known-advisory morag=within-support\n"
    f"SHIP {C} xandar=no-known-advisory morag=maintainer-backport\n"
    "REFUSE 8.1.2 xandar=identity-is-not-a-digest morag=identity-is-not-a-digest\n"
    "day 20800: 2 of 4 ship, 1 malformed lines\n"
)


class ExampleAppTests(unittest.TestCase):
    built: dict[str, Path] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = tempfile.TemporaryDirectory(prefix="koschei-apps-")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.workspace.cleanup()

    def ks_run(self, app: str, args: list[str], data: bytes) -> str:
        stdout = io.StringIO()
        stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stream), redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(ROOT / app / "main.ks"), *args])
        self.assertEqual(code, 0, errors.getvalue())
        return stdout.getvalue()

    def native(self, app: str, args: list[str], data: bytes) -> str | None:
        if GO is None:
            return None
        binary = self.built.get(app)
        if binary is None:
            binary = Path(self.workspace.name) / app
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(cli_main(["build", str(ROOT / app / "main.ks"), "-o", str(binary)]), 0, errors.getvalue())
            self.built[app] = binary
        completed = subprocess.run([str(binary), *args], input=data, capture_output=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.decode("utf-8")

    def both(self, app: str, args: list[str], data: bytes, expected: str) -> None:
        self.assertEqual(self.ks_run(app, args, data), expected)
        native = self.native(app, args, data)
        if native is not None:
            self.assertEqual(native, expected)

    def test_wordfreq(self) -> None:
        text = b"the cat saw the dog\nthe end\n"
        self.both("wordfreq", [], text, "1 cat\n1 dog\n1 end\n1 saw\n3 the\n7 words, 5 reported\n")
        self.both("wordfreq", ["2"], text, "3 the\n7 words, 1 reported\n")
        self.both("wordfreq", ["0"], text, "wordfreq: usage: wordfreq [MINIMUM] < text\n")
        self.both("wordfreq", [], b"\xff", "wordfreq: usage: wordfreq [MINIMUM] < text\n")

    def test_release_gate(self) -> None:
        self.both("release_gate", ["20800"], GATE.encode(), GATE_OUTPUT)
        self.both("release_gate", ["soon"], b"", "release_gate: DAY must be a day number\n")
        self.both("release_gate", ["20800"], b"", "day 20800: 0 of 0 ship, 0 malformed lines\n")

    def test_keygen(self) -> None:
        for output in (self.ks_run("keygen", ["3"], b""), self.native("keygen", ["3"], b"")):
            if output is None:
                continue
            lines = output.splitlines()
            self.assertEqual(lines[-1], "3 keys issued")
            keys = []
            for line in lines[:-1]:
                match = re.fullmatch(r"key=([0-9a-f]{64}) fingerprint=(sha3-256:[0-9a-f]{64})", line)
                self.assertIsNotNone(match, line)
                key, fingerprint = match.groups()
                self.assertEqual(fingerprint, secure_digest("koschei.example.keygen/v1", [key]))
                keys.append(key)
            self.assertEqual(len(set(keys)), 3)
        self.both("keygen", ["17"], b"", "keygen: usage: keygen [COUNT 1..16]\n")

    def test_manifests_grant_only_what_each_app_needs(self) -> None:
        expected = {
            "wordfreq": {"PROGRAM GİRDİSİ"},
            "release_gate": {"PROGRAM GİRDİSİ", "SAAT"},
            "keygen": {"PROGRAM GİRDİSİ", "RASTGELE SAYI"},
        }
        for app, granted in expected.items():
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                self.assertEqual(cli_main(["caps", str(ROOT / app / "main.ks")]), 0)
            titles = {
                line[:-1] for line in stdout.getvalue().splitlines()
                if line.endswith(":") and not line.startswith(" ") and "MANİFESTO" not in line
            }
            self.assertEqual(titles - {"YETKİ TAŞIYAN FONKSİYONLAR"}, granted, app)


if __name__ == "__main__":
    unittest.main()
