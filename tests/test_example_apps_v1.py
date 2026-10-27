"""The example applications run, compile and agree with their native binaries."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import os
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


# Credential-shaped test values are assembled at run time, so no scanner
# (GitHub push protection included) mistakes this file for a leak.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "gh" + "p_" + "0123456789abcdefghijABCDEFGHIJ012345"
SLACK_TOKEN = "xo" + "xb-" + "123456789012-abcdef"
STRIPE_KEY = "sk_" + "live_" + "0123456789abcdefABCDEF"
GOOGLE_KEY = "AI" + "zaSyA-1234567890abcdefghijklmnopqrstu"
PEM_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"


def chunked_digest(data: bytes) -> str:
    if len(data) <= 1 << 20:
        return digest_bytes(data)
    parts = [digest_bytes(data[start:start + (1 << 20)]) for start in range(0, len(data), 1 << 20)]
    return secure_digest("koschei.example.integrity.chunks/v1", parts)


def digest_bytes(data: bytes) -> str:
    return "sha3-256:" + hashlib.sha3_256(data).hexdigest()


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

    def outcome(self, app: str, args: list[str], data: bytes = b"") -> tuple[int, str, str]:
        """(exit status, stdout, stderr), the same under ks run and natively."""
        stdout = io.StringIO()
        stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stream), redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
            code = cli_main(["run", str(ROOT / app / "main.ks"), *args])
        interpreted = (code, stdout.getvalue(), errors.getvalue())
        if GO is not None:
            binary = self.built.get(app)
            if binary is None:
                binary = Path(self.workspace.name) / app
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as build_errors:
                    self.assertEqual(cli_main(["build", str(ROOT / app / "main.ks"), "-o", str(binary)]), 0, build_errors.getvalue())
                self.built[app] = binary
            completed = subprocess.run([str(binary), *args], input=data, capture_output=True, timeout=60, check=False)
            native = (completed.returncode, completed.stdout.decode("utf-8"), completed.stderr.decode("utf-8"))
            self.assertEqual(native, interpreted)
        return interpreted

    def tree(self, files: dict[str, bytes]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="tree-", dir=self.workspace.name))
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return root

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

    def test_secretscan(self) -> None:
        root = self.tree({
            "src/app.py": f'aws_key = "{AWS_KEY}"\nok = 1\n'.encode(),
            "conf/ci.yml": f"token: {GITHUB_TOKEN}\nslack={SLACK_TOKEN}\n".encode(),
            "conf/id_rsa": f"{PEM_HEADER}\nMIIabc\n".encode(),
            "conf/sa.json": ('{"private_key": "-----BEGIN ' + 'PRIVATE KEY-----\\nMIIE"}\n').encode(),
            "src/keys.js": f'key = "{GOOGLE_KEY}"\nstripe = {STRIPE_KEY}\nnot: AKIAshort\n'.encode(),
            "src/scanner.py": b'if line.contains("-----BEGIN ") && line.contains("PRIVATE KEY-----")\n',
            ".git/config": AWS_KEY.encode(),
            "bin.dat": b"\xff\xfe",
        })
        os.symlink(root / "src" / "app.py", root / "src" / "link.py")
        self.assertEqual(self.outcome("secretscan", [str(root)]), (
            1,
            f"{root}/conf/ci.yml:1: github-token ghp_... (40 characters)\n"
            f"{root}/conf/ci.yml:2: slack-token xoxb-... (24 characters)\n"
            f"{root}/conf/id_rsa:1: private-key {PEM_HEADER}\n"
            f"{root}/conf/sa.json:1: private-key -----BEGIN PRIVATE KEY-----\n"
            f"{root}/src/app.py:1: aws-access-key-id AKIA... (20 characters)\n"
            f"{root}/src/keys.js:1: google-api-key AIza... (39 characters)\n"
            f"{root}/src/keys.js:2: stripe-live-key sk_live_... (30 characters)\n"
            "6 files scanned, 2 skipped, 7 findings\n",
            "KOSCHEI RUNTIME ERROR: secretscan: 7 credential(s) found\n",
        ))
        clean = self.tree({"a.txt": b"nothing here\n"})
        self.assertEqual(self.outcome("secretscan", [str(clean)]), (0, "1 files scanned, 0 skipped, 0 findings\n", ""))
        missing = str(clean / "missing")
        self.assertEqual(self.outcome("secretscan", [missing]), (1, "", f"KOSCHEI RUNTIME ERROR: secretscan: {missing} is not a readable directory\n"))
        self.assertEqual(self.outcome("secretscan", []), (1, "", "KOSCHEI RUNTIME ERROR: usage: secretscan DIR\n"))

    def test_integrity(self) -> None:
        large = bytes(range(256)) * 10000  # 2.5 MiB: digested in chunks
        files = {"a.txt": b"alpha\n", "sub/b.txt": b"beta\n", "sub/large.bin": large, ".git/HEAD": b"x"}
        root = self.tree(files)
        os.symlink(root / "a.txt", root / "sub" / "link")
        code, manifest, errors = self.outcome("integrity", ["snapshot", str(root)])
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(manifest, (
            f"{digest_bytes(b'alpha' + bytes([10]))} a.txt\n"
            f"{digest_bytes(b'beta' + bytes([10]))} sub/b.txt\n"
            f"{chunked_digest(large)} sub/large.bin\n"
            "skipped sub/link\n"
        ))
        self.assertEqual(self.outcome("integrity", ["verify", str(root)], manifest.encode()), (0, "4 entries checked, 0 differences\n", ""))
        (root / "a.txt").write_bytes(b"alpha!\n")
        (root / "sub" / "b.txt").unlink()
        (root / "new.txt").write_bytes(b"new\n")
        self.assertEqual(self.outcome("integrity", ["verify", str(root)], manifest.encode()), (
            1,
            "CHANGED a.txt\nNEW new.txt\nMISSING sub/b.txt\n4 entries checked, 3 differences\n",
            "KOSCHEI RUNTIME ERROR: integrity: 3 difference(s)\n",
        ))
        self.assertEqual(
            self.outcome("integrity", ["verify", str(root)], b"garbage\n"),
            (1, "", "KOSCHEI RUNTIME ERROR: integrity: malformed manifest line: garbage\n"),
        )
        self.assertEqual(self.outcome("integrity", ["check", str(root)])[0], 1)

    def test_manifests_grant_only_what_each_app_needs(self) -> None:
        expected = {
            "wordfreq": {"PROGRAM GİRDİSİ"},
            "release_gate": {"PROGRAM GİRDİSİ", "SAAT"},
            "keygen": {"PROGRAM GİRDİSİ", "RASTGELE SAYI"},
            # Read-only disk and no network: what they find cannot leave.
            "secretscan": {"PROGRAM GİRDİSİ", "DİSK"},
            "integrity": {"PROGRAM GİRDİSİ", "DİSK"},
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
