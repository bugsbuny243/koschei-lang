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


def load_source(target: Path, *, propagate_error: bool = False) -> str:
    if propagate_error:
        body = "    let loaded = state.load() or return\n"
    else:
        body = '    let loaded = state.load() or ""\n    println(loaded)\n'
    return f"""
fn main(caps: SystemCaps) {{
    let state = caps.persist.allow({ks_string(str(target))}, 4096, 2000)
{body}}}
"""


class PersistenceNativeExactObjectShapeTests(unittest.TestCase):
    def test_generated_runtime_rejects_silent_path_rewrite_and_hard_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("ok", encoding="utf-8")
            program = parse(load_source(target))
            check(program)
            generated = generate_go(program)

        self.assertIn("raw != strings.TrimSpace(raw)", generated)
        self.assertIn("canonical != raw", generated)
        self.assertGreaterEqual(generated.count("info.Nlink != 1"), 2)
        self.assertIn("exactly one hard-link name", generated)


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native exact-object testleri atlandı")
@unittest.skipUnless(__import__("sys").platform.startswith("linux"), "Native persistence v1 Linux-only")
class PersistenceNativeExactObjectRuntimeTests(unittest.TestCase):
    def build(self, source: str) -> Path:
        program = parse(source)
        check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-exact-")
        self.addCleanup(workspace.cleanup)
        root = Path(workspace.name)
        (root / "main.go").write_text(generated, encoding="utf-8")
        (root / "go.mod").write_text("module koscheipersistexact\n\ngo 1.21\n", encoding="utf-8")
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

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_native_load_rejects_hard_link_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = root / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            target = root / "state.txt"
            os.link(secret, target)

            binary = self.build(load_source(target, propagate_error=True))
            completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("KS3420", completed.stderr)
            self.assertIn("hard-link", completed.stderr)
            self.assertEqual(secret.read_text(encoding="utf-8"), "secret")
            self.assertEqual(target.read_text(encoding="utf-8"), "secret")


if __name__ == "__main__":
    unittest.main()
