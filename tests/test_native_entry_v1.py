"""An Error returned by main fails a native binary as it fails `ks run`."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")

PROGRAMS = {
    "plain": 'fn main() -> Error {\n    println("a")\n    return Error("failed")\n}\n',
    "broker": (
        'fn main(caps: SystemCaps) -> Error {\n    println(caps.env.allow("KS_ENTRY").get() or "?")\n'
        '    return Error("failed too")\n}\n'
    ),
    "success": 'fn main() -> String or Error {\n    return "ok"\n}\n',
}


@unittest.skipIf(GO is None, "Go toolchain is not installed")
class NativeEntryTests(unittest.TestCase):
    def test_main_results_match_ks_run(self) -> None:
        environment = dict(os.environ, PYTHONPATH=str(ROOT), KS_ENTRY="x")
        for name, source in PROGRAMS.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                (base / "main.ks").write_text(source, encoding="utf-8")
                run = subprocess.run(
                    [sys.executable, "-m", "koschei", "run", "main.ks"], cwd=base, env=environment,
                    capture_output=True, timeout=120, check=False,
                )
                build = subprocess.run(
                    [sys.executable, "-m", "koschei", "build", "main.ks", "-o", "app"], cwd=base,
                    env=environment, capture_output=True, timeout=300, check=False,
                )
                self.assertEqual(build.returncode, 0, build.stderr.decode())
                native = subprocess.run(
                    [str(base / "app")], cwd=base, env=environment, capture_output=True, timeout=60, check=False,
                )
                self.assertEqual((native.returncode, native.stdout, native.stderr), (run.returncode, run.stdout, run.stderr))
                self.assertEqual(run.returncode, 0 if name == "success" else 1)


if __name__ == "__main__":
    unittest.main()
