from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from koschei.codegen_go import CodegenError, generate_go
from koschei.parser import parse
from koschei.semantic import check


GO_BINARY = shutil.which("go")


def ks_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def source_for(target: Path, *, max_bytes: int = 4096, payload: str = "hello") -> str:
    return f"""
fn main(caps: SystemCaps) {{
    let state = caps.persist.allow({ks_string(str(target))}, {max_bytes}, 2000)
    let wrote = state.commit({ks_string(payload)}) or return
    let loaded = state.load() or ""
    println(loaded)
}}
"""


class PersistenceNativeGoShapeTests(unittest.TestCase):
    def test_linux_codegen_contains_descriptor_bound_commit_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            program = parse(source_for(target))
            check(program)
            with patch("koschei.persistence_native_go_v1.sys.platform", "linux"):
                generated = generate_go(program)

        self.assertIn('"crypto/rand"', generated)
        self.assertIn('"encoding/hex"', generated)
        self.assertIn("type ksPersistCaps struct", generated)
        self.assertIn("ksPersistOPath|syscall.O_NOFOLLOW", generated)
        self.assertIn("syscall.O_NONBLOCK|syscall.O_NOFOLLOW", generated)
        self.assertIn("syscall.Renameat(parentFD, tempName, parentFD, capability.name)", generated)
        self.assertIn("syscall.Unlinkat(parentFD, tempName)", generated)
        self.assertIn("syscall.Fsync(tempFD)", generated)
        self.assertIn("syscall.Fsync(parentFD)", generated)
        self.assertIn("KS3423", generated)

    def test_non_linux_native_persistence_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            program = parse(source_for(Path(temporary) / "state.txt"))
            check(program)
            with patch("koschei.persistence_native_go_v1.sys.platform", "darwin"):
                with self.assertRaises(CodegenError) as context:
                    generate_go(program)
        self.assertEqual(context.exception.code, "KS4001")


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native persistence testleri atlandı")
@unittest.skipUnless(__import__("sys").platform.startswith("linux"), "Native persistence v1 Linux-only")
class PersistenceNativeGoRuntimeTests(unittest.TestCase):
    def build(self, source: str) -> Path:
        program = parse(source)
        check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-persist-")
        self.addCleanup(workspace.cleanup)
        root = Path(workspace.name)
        (root / "main.go").write_text(generated, encoding="utf-8")
        (root / "go.mod").write_text("module koscheipersist\n\ngo 1.21\n", encoding="utf-8")
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

    def execute(self, source: str) -> subprocess.CompletedProcess[str]:
        binary = self.build(source)
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)

    def test_native_commit_and_load_round_trip_matches_exact_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            completed = self.execute(source_for(target, payload='{"v":1}'))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, '{"v":1}\n')
            self.assertEqual(completed.stderr, "")
            self.assertEqual(target.read_text(encoding="utf-8"), '{"v":1}')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual([item.name for item in target.parent.iterdir() if item.name.startswith(".koschei-persist-")], [])

    def test_native_byte_budget_fails_before_old_state_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            completed = self.execute(source_for(target, max_bytes=4, payload="12345"))
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("KS3421", completed.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_native_final_symlink_is_rejected_without_touching_external_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            target = root / "state.txt"
            try:
                target.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            completed = self.execute(source_for(target, payload="blocked"))
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("KS3420", completed.stderr)
            self.assertEqual(outside.read_text(encoding="utf-8"), "secret")
            self.assertTrue(target.is_symlink())

    def test_native_invalid_utf8_load_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.bin"
            target.write_bytes(b"\xff")
            source = f"""
fn main(caps: SystemCaps) {{
    let state = caps.persist.allow({ks_string(str(target))}, 4096, 2000)
    let loaded = state.load() or return
}}
"""
            completed = self.execute(source)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("KS3420", completed.stderr)

    def test_native_parent_symlink_component_does_not_redirect_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            completed = self.execute(source_for(link / "state.txt", payload="blocked"))
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("KS3424", completed.stderr)
            self.assertFalse((real / "state.txt").exists())


if __name__ == "__main__":
    unittest.main()
