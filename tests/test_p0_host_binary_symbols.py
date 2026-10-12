"""P0.1 evidence test: inspect *compiled* native Go symbols, not source selectors.

This intentionally does not claim that absent names prove sandbox isolation.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

from koschei.codegen_go import generate_go
from koschei.parser import parse
from koschei.semantic import check


GO = shutil.which("go")
ROOT = pathlib.Path(__file__).resolve().parents[1]
WATCHED = (
    "syscall.Openat",
    "syscall.Close",
    "syscall.Socket",
    "syscall.Bind",
    "syscall.Listen",
    "syscall.Renameat",
    "syscall.Unlinkat",
    "os.NewFile",
    "os.LookupEnv",
    "os.Remove",
    "io.ReadAll",
    "net.Dial",
    "net/http.NewRequest",
)


@unittest.skipUnless(GO, "Go unavailable: native artifact measurement not run")
class HostSymbolEvidenceTests(unittest.TestCase):
    def test_pure_program_binary_symbol_receipt(self) -> None:
        source = (ROOT / "examples" / "hello.ks").read_text(encoding="utf-8")
        program = parse(source)
        check(program)
        generated = generate_go(program)
        with tempfile.TemporaryDirectory(prefix="koschei-p0-host-") as tmp:
            work = pathlib.Path(tmp)
            (work / "main.go").write_text(generated, encoding="utf-8")
            (work / "go.mod").write_text(
                "module koscheihostsurface\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = work / "program"
            version = subprocess.run(
                [GO, "version"], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(version.returncode, 0, version.stderr)
            built = subprocess.run(
                [GO, "build", "-o", str(binary), "."],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            nm = subprocess.run(
                [GO, "tool", "nm", str(binary)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(nm.returncode, 0, nm.stderr)
            symbols = [
                line.split(maxsplit=2)[-1]
                for line in nm.stdout.splitlines()
                if len(line.split(maxsplit=2)) == 3
            ]
            self.assertTrue(symbols, "go tool nm returned no symbols")
            present = tuple(
                name for name in WATCHED
                if any(symbol == name or symbol.startswith(name + ".") for symbol in symbols)
            )
            absent = tuple(name for name in WATCHED if name not in present)
            print(
                "P0_HOST_SYMBOL_RECEIPT "
                f"go={version.stdout.strip()!r} "
                f"fixture='examples/hello.ks' "
                f"present={present!r} absent={absent!r}"
            )
            self.assertEqual(set(present) | set(absent), set(WATCHED))
            self.assertFalse(set(present) & set(absent))


if __name__ == "__main__":
    unittest.main()
