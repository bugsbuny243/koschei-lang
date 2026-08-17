from __future__ import annotations

import json
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


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native persistence alignment testi atlandı")
@unittest.skipUnless(__import__("sys").platform.startswith("linux"), "Native persistence v1 Linux-only")
class PersistenceNativeAuthorityAlignmentV1Tests(unittest.TestCase):
    def test_missing_parent_still_crosses_function_boundary_as_persist_caps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "missing-parent" / "state.txt"
            source = f"""
fn use(state: PersistCaps) -> String or Error {{
    return state.load() or return
}}

fn main(caps: SystemCaps) {{
    let state = caps.persist.allow({ks_string(str(target))}, 4096, 2000)
    let value = use(state) or return
}}
"""
            program = parse(source)
            check(program)
            generated = generate_go(program)

            workspace = tempfile.TemporaryDirectory(prefix="koschei-persist-align-")
            self.addCleanup(workspace.cleanup)
            root = Path(workspace.name)
            (root / "main.go").write_text(generated, encoding="utf-8")
            (root / "go.mod").write_text("module koscheipersistalign\n\ngo 1.21\n", encoding="utf-8")
            binary = root / "program"
            built = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(built.returncode, 0, built.stderr)

            completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("KS3424", completed.stderr)
            self.assertNotIn("KS3106", completed.stderr)


if __name__ == "__main__":
    unittest.main()
