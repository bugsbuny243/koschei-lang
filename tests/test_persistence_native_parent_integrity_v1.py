from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.codegen_go import generate_go
from koschei.parser import parse
from koschei.semantic import check


GO_BINARY = shutil.which("go")


def ks_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def source_for(target: Path) -> str:
    return f"""
fn main(caps: SystemCaps) {{
    let state = caps.persist.allow({ks_string(str(target))}, 4096, 2000)
    let wrote = state.commit("native") or return
    let loaded = state.load() or ""
    println(loaded)
}}
"""


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native parent integrity testleri atlandı")
@unittest.skipUnless(__import__("sys").platform.startswith("linux"), "Native persistence v1 Linux-only")
class PersistenceNativeParentIntegrityV1Tests(unittest.TestCase):
    def build(self, source: str) -> Path:
        program = parse(source)
        check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-parent-")
        self.addCleanup(workspace.cleanup)
        root = Path(workspace.name)
        (root / "main.go").write_text(generated, encoding="utf-8")
        (root / "go.mod").write_text("module koscheipersistparent\n\ngo 1.21\n", encoding="utf-8")
        binary = root / "program"
        completed = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return binary

    def test_non_sticky_shared_parent_fails_before_state_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "shared"
            parent.mkdir(mode=0o700)
            os.chmod(parent, 0o777)
            target = parent / "state.txt"
            target.write_text("old", encoding="utf-8")

            binary = self.build(source_for(target))
            completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("KS3420", completed.stderr)
            self.assertIn("group/world-writable", completed.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_sticky_shared_parent_remains_admissible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "sticky"
            parent.mkdir(mode=0o700)
            os.chmod(parent, 0o1777)
            target = parent / "state.txt"

            binary = self.build(source_for(target))
            completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "native\n")
            self.assertEqual(completed.stderr, "")
            self.assertEqual(target.read_text(encoding="utf-8"), "native")


if __name__ == "__main__":
    unittest.main()
