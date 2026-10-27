"""`disk.read` returns text or an Error value, never a host exception.

A String holds UTF-8 text. A file whose bytes are not valid UTF-8 used to end
the program with a host `UnicodeDecodeError`, reported as a compiler error and
impossible to catch with `or`. It is now an ordinary Error value.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main as cli_main
from koschei.interpreter import DiskCaps, KsError

PROGRAM = """
fn main(caps: SystemCaps) {
    let disk = caps.disk.allow_read_only(".") or return
    let caught = disk.read("blob.bin") or "STOP"
    println(caught)
    let late = disk.read("late.bin")
    println(late)
    let text = disk.read("text.txt") or "?"
    println(text)
}
"""


class DiskReadTextTests(unittest.TestCase):
    def test_invalid_utf8_is_an_error_value(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-disk-text-") as directory:
            root = Path(directory)
            (root / "blob.bin").write_bytes(b"\xff\xfe\x00binary")
            (root / "late.bin").write_bytes("geçerli başlangıç ".encode("utf-8") + b"\xc3")
            (root / "text.txt").write_text("çğü", encoding="utf-8")
            (root / "main.ks").write_text(PROGRAM, encoding="utf-8")
            previous = os.getcwd()
            os.chdir(root)
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(io.StringIO()) as errors:
                    code = cli_main(["run", str(root / "main.ks")])
            finally:
                os.chdir(previous)
            capability = DiskCaps(str(root))
            direct = capability.read_file(str(root / "blob.bin"))
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(
            stdout.getvalue(),
            "STOP\nDosya okunamadı: geçerli UTF-8 metin değil: late.bin\nçğü\n",
        )
        self.assertIsInstance(direct, KsError)


if __name__ == "__main__":
    unittest.main()
