"""`ks build` produces statically linked binaries.

A binary built with cgo enabled (Go's default when a C compiler is present)
needs the host's glibc and its dynamic loader: it does not start on a musl
host or in an image that holds only the binary. Every brokered domain is
checked, because the network runtime is what pulled in the C resolver.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

ROOT = Path(__file__).resolve().parent.parent
PT_INTERP = 3
PT_DYNAMIC = 2


def program_header_types(binary: bytes) -> set[int]:
    """Program header types of a 64-bit little-endian ELF file."""
    if binary[:4] != b"\x7fELF" or binary[4] != 2 or binary[5] != 1:
        raise ValueError("not a 64-bit little-endian ELF file")
    phoff = struct.unpack_from("<Q", binary, 0x20)[0]
    phentsize, phnum = struct.unpack_from("<HH", binary, 0x36)
    return {struct.unpack_from("<I", binary, phoff + index * phentsize)[0] for index in range(phnum)}


@unittest.skipIf(shutil.which("go") is None, "Go toolchain is not installed")
class NativeStaticBuildTests(unittest.TestCase):
    def build(self, source: Path, target: Path) -> bytes:
        # Even when the caller's environment asks for cgo.
        previous = os.environ.get("CGO_ENABLED")
        os.environ["CGO_ENABLED"] = "1"
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(cli_main(["build", str(source), "-o", str(target)]), 0, errors.getvalue())
        finally:
            if previous is None:
                os.environ.pop("CGO_ENABLED", None)
            else:
                os.environ["CGO_ENABLED"] = previous
        return target.read_bytes()

    def test_binaries_are_static(self) -> None:
        fixtures = {
            "pure": ROOT / "examples" / "hello.ks",
            "environment broker": ROOT / "examples" / "runtime_demo.ks",
            "network": ROOT / "examples" / "capability.ks",
        }
        with tempfile.TemporaryDirectory() as workspace:
            for label, source in fixtures.items():
                with self.subTest(fixture=label):
                    binary = self.build(source, Path(workspace) / label.replace(" ", "_"))
                    kinds = program_header_types(binary)
                    self.assertNotIn(PT_INTERP, kinds, "binary asks for a dynamic loader")
                    self.assertNotIn(PT_DYNAMIC, kinds, "binary links shared libraries")

    def test_static_binary_runs_without_a_loader(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            target = Path(workspace) / "hello"
            self.build(ROOT / "examples" / "hello.ks", target)
            # An empty environment and no library path: nothing to resolve.
            completed = subprocess.run([str(target)], env={}, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout)


if __name__ == "__main__":
    unittest.main()
