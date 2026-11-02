"""HMAC-SHA256, PBKDF2-HMAC-SHA256 and constant-time equality (password_hash_v1).

The digests come from the platform providers; these tests pin them to
published vectors, fix the PBKDF2 parameter bounds and their order, and
require the same bytes from every `ks run` executor and from native binaries.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from koschei import runtime_budget
from koschei.canonical_mir_budget_runtime_v1 import _run_budgeted_canonical_mir
from koschei.cli_entry import main as cli
from koschei.diagnostics import lookup
from koschei.interpreter import Bytes, KsError
from koschei.mir_native_variant_construct_v1 import inspect_native_mir_support, run_mir_native
from koschei.modules import check_graph, load_graph
from koschei.password_hash_v1 import (
    ITERATIONS_MESSAGE,
    KEY_MESSAGE,
    PASSWORD_MESSAGE,
    SALT_MESSAGE,
    hmac_sha256,
    pbkdf2_sha256,
    secure_equal,
)

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

# RFC 4231 test cases 1, 2 and 6 (a key longer than the block size).
HMAC_VECTORS = (
    ("0b" * 20, b"Hi There".hex(), "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
    (b"Jefe".hex(), b"what do ya want for nothing?".hex(),
     "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
    ("aa" * 131, b"Test Using Larger Than Block-Size Key - Hash Key First".hex(),
     "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
)

SALT = "73616c742d6f662d313662797465732d"  # "salt-of-16bytes-"

PROGRAM = (
    "fn main() {\n"
    + "".join(
        f'    let key{index} = bytes_from_hex("{key}") or return\n'
        f'    let data{index} = bytes_from_hex("{data}") or return\n'
        f"    println(hmac_sha256(key{index}, data{index}))\n"
        for index, (key, data, _) in enumerate(HMAC_VECTORS)
    )
    + f'    let salt = bytes_from_hex("{SALT}") or return\n'
    '    let password = bytes_from_hex("68756e74657232") or return\n'
    "    let empty = bytes_from_hex(\"\") or return\n"
    "    let short = bytes_from_hex(\"00ff\") or return\n"
    "    let hash = pbkdf2_sha256(password, salt, 100000, 32) or return\n"
    "    println(hash)\n"
    "    println(pbkdf2_sha256(empty, salt, 100000, 16))\n"
    "    println(pbkdf2_sha256(password, short, 99999, 8))\n"
    "    println(pbkdf2_sha256(password, salt, 99999, 8))\n"
    "    println(pbkdf2_sha256(password, salt, 10000001, 32))\n"
    "    println(pbkdf2_sha256(password, salt, 100000, 65))\n"
    "    println(pbkdf2_sha256(password, salt, 100000, 15))\n"
    "    let again = pbkdf2_sha256(password, salt, 100000, 32) or return\n"
    "    println(secure_equal(hash, again))\n"
    '    println(secure_equal(hash, "{hash}x"))\n'
    '    println(secure_equal("", ""))\n'
    '    println(secure_equal("ğ", "ğ"))\n'
    '    println(secure_equal("a", "b"))\n'
    "}\n"
)


def _expected() -> str:
    salt, password = bytes.fromhex(SALT), b"hunter2"
    lines = [digest for _, _, digest in HMAC_VECTORS]
    lines += [
        hashlib.pbkdf2_hmac("sha256", password, salt, 100000, 32).hex(),
        hashlib.pbkdf2_hmac("sha256", b"", salt, 100000, 16).hex(),
        SALT_MESSAGE,
        ITERATIONS_MESSAGE,
        ITERATIONS_MESSAGE,
        KEY_MESSAGE,
        KEY_MESSAGE,
        "true", "false", "true", "true", "false",
    ]
    return "".join(f"{line}\n" for line in lines)


EXPECTED = _expected()


def _write(directory: str, source: str) -> Path:
    path = Path(directory) / "main.ks"
    path.write_text(source, encoding="utf-8")
    return path


class PasswordHashOperationTests(unittest.TestCase):
    def test_hmac_matches_rfc_4231(self) -> None:
        for key, data, digest in HMAC_VECTORS:
            with self.subTest(digest=digest):
                self.assertEqual(hmac_sha256(Bytes(bytes.fromhex(key)), Bytes(bytes.fromhex(data))), digest)

    def test_pbkdf2_bounds_are_checked_salt_iterations_key_then_password(self) -> None:
        salt, password = Bytes(bytes.fromhex(SALT)), Bytes(b"pw")
        for arguments, message in (
            ((password, Bytes(b"x" * 15), 1, 1), SALT_MESSAGE),
            ((password, Bytes(b"x" * 1025), 100000, 32), SALT_MESSAGE),
            ((password, salt, 1, 1), ITERATIONS_MESSAGE),
            ((password, salt, 100000, 1), KEY_MESSAGE),
            ((Bytes(b"p" * 4097), salt, 100000, 64), PASSWORD_MESSAGE),
        ):
            with self.subTest(message=message):
                result = pbkdf2_sha256(*arguments)
                self.assertIsInstance(result, KsError)
                self.assertEqual(result.message, message)
        self.assertEqual(
            pbkdf2_sha256(Bytes(b"p" * 4096), Bytes(b"s" * 1024), 100000, 64),
            hashlib.pbkdf2_hmac("sha256", b"p" * 4096, b"s" * 1024, 100000, 64).hex(),
        )

    def test_secure_equal_compares_utf8_bytes(self) -> None:
        self.assertTrue(secure_equal("ğ", "ğ"))
        self.assertFalse(secure_equal("ğ", "g"))
        self.assertFalse(secure_equal("abc", "abcd"))

    def test_the_checker_types_every_argument(self) -> None:
        head = 'fn main() {\n    let b = bytes_from_hex("00") or return\n'
        for line in (
            '    println(hmac_sha256("key", b))\n',
            "    println(hmac_sha256(b))\n",
            "    println(pbkdf2_sha256(b, b, 100000))\n",
            '    println(pbkdf2_sha256(b, b, "100000", 32))\n',
            "    println(secure_equal(b, b))\n",
            "    let hash = pbkdf2_sha256(b, b, 100000, 32)\n    println(hash.length())\n",
        ):
            with self.subTest(line=line.strip()), tempfile.TemporaryDirectory() as directory:
                path = _write(directory, head + line + "}\n")
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli(["check", str(path)]), 1, output.getvalue())
                self.assertRegex(output.getvalue(), "KS1301|KS1306|KS1401|KS1502")

    def test_the_bounds_are_explained(self) -> None:
        for language in ("en", "tr"):
            with self.subTest(language=language):
                self.assertIn("600000", lookup("KS3490", language).fix)


class PasswordHashExecutorTests(unittest.TestCase):
    def test_every_ks_run_executor_hashes_the_same(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write(directory, PROGRAM)
            graph = load_graph(path)
            check_graph(graph)
            mir = graph.mir
            root = mir.root_module
            self.assertTrue(inspect_native_mir_support(mir).supported)
            runs = {
                "ks run": lambda: cli(["run", str(path)]),
                "canonical": lambda: _run_budgeted_canonical_mir(mir, [], runtime_budget.RuntimeBudget()),
                "ast": lambda: runtime_budget.BudgetedInterpreter(
                    root.program,
                    [],
                    namespaces=mir.namespaces(),
                    imports=dict(root.imports),
                    enums=mir.enums(),
                    module_imports=mir.module_imports(),
                    structs=mir.structs(),
                    budget=runtime_budget.RuntimeBudget(),
                ).execute_main(),
                "direct": lambda: run_mir_native(mir),
            }
            for name, run in runs.items():
                with self.subTest(executor=name):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                        with runtime_budget.host_recursion_headroom():
                            run()
                    self.assertEqual(stdout.getvalue(), EXPECTED)

    @unittest.skipUnless(GO, "Go is not installed")
    def test_binaries_hash_like_ks_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _write(directory, PROGRAM)
            build = subprocess.run(
                [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"],
                cwd=directory, env=dict(os.environ, PYTHONPATH=str(ROOT)),
                capture_output=True, timeout=300, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr.decode())
            native = subprocess.run([str(Path(directory) / "app")], capture_output=True, timeout=60, check=False)
            self.assertEqual(
                (native.returncode, native.stdout.decode(), native.stderr.decode()), (0, EXPECTED, "")
            )


if __name__ == "__main__":
    unittest.main()
