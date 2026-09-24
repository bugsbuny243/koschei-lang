from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from koschei import cli as legacy_cli
from koschei.cli_entry import main as cli_main, native_build_mode
from koschei.mir import require_mir
from koschei.mir_go_native import generate_go_mir_native, inspect_mir_go_support
from koschei.modules import check_graph, load_graph


REPO_ROOT = Path(__file__).resolve().parents[1]


class MirGoNativeTests(unittest.TestCase):
    def checked_mir(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "main.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        return path, require_mir(graph)

    def test_hello_is_supported_and_go_source_has_mir_state_machine(self) -> None:
        graph = load_graph(REPO_ROOT / "examples" / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)
        support = inspect_mir_go_support(mir)
        self.assertTrue(support.supported, support.reasons)
        self.assertEqual(native_build_mode(mir), "mir_go_v1")

        source = generate_go_mir_native(mir)
        self.assertIn("Code generated from sealed Koschei MIR v4", source)
        self.assertIn("switch _ks_pc", source)
        self.assertIn("fmt.Println", source)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is required")
    def test_public_build_uses_mir_go_without_legacy_ast_codegen(self) -> None:
        source = REPO_ROOT / "examples" / "hello.ks"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "hello-native"
            output = io.StringIO()
            with patch.object(
                legacy_cli,
                "command_build",
                side_effect=AssertionError("legacy AST-Go path must not run"),
            ), redirect_stdout(output):
                code = cli_main(["build", str(source), "-o", str(target)])
            self.assertEqual(code, 0)
            self.assertTrue(target.is_file())
            completed = subprocess.run(
                [str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "Koschei\n1\n")

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is required")
    def test_shadowed_bindings_compile_directly_from_mir_go(self) -> None:
        source, mir = self.checked_mir(
            """
fn main() {
    let x = 1
    if true {
        let x = 2
        println(x)
    }
    println(x)
}
"""
        )
        support = inspect_mir_go_support(mir)
        self.assertTrue(support.supported, support.reasons)
        self.assertEqual(native_build_mode(mir), "mir_go_v1")

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "shadow-native"
            with patch.object(
                legacy_cli,
                "command_build",
                side_effect=AssertionError("legacy AST-Go path must not run"),
            ):
                code = cli_main(["build", str(source), "-o", str(target)])
            self.assertEqual(code, 0)
            completed = subprocess.run(
                [str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "2\n1\n")

    def test_normalized_for_loop_fails_closed_instead_of_legacy_ast_codegen(self) -> None:
        _, mir = self.checked_mir(
            """
fn main() {
    for value in [1, 2, 3] {
        println(value)
    }
}
"""
        )
        support = inspect_mir_go_support(mir)
        self.assertFalse(support.supported)
        self.assertEqual(native_build_mode(mir), "blocked_ambient_ast_go_v1")
        self.assertFalse(any("AST fallback" in reason for reason in support.reasons))
        self.assertTrue(
            any("MirList" in reason or "MirIter" in reason for reason in support.reasons),
            support.reasons,
        )

    def test_local_calls_and_loop_cfg_are_emitted_from_mir(self) -> None:
        _, mir = self.checked_mir(
            """
fn twice(value: Int) -> Int {
    return value * 2
}

fn main() {
    let mut n = 0
    while n < 3 {
        n = n + 1
        if n == 2 {
            continue
        }
        println(twice(n))
    }
}
"""
        )
        support = inspect_mir_go_support(mir)
        self.assertTrue(support.supported, support.reasons)
        go_source = generate_go_mir_native(mir)
        self.assertIn("_ks_pc =", go_source)
        self.assertIn("continue", go_source)
        self.assertNotIn("MirAstFallback", go_source)

    def test_user_enum_match_is_supported_from_sealed_mir(self) -> None:
        _, mir = self.checked_mir(
            """
enum State {
    Ready(Int),
    Idle,
}

fn main() {
    println(match Ready(99) {
        Ready(value) => value,
        Idle => 0,
    })
}
"""
        )
        support = inspect_mir_go_support(mir)
        self.assertTrue(support.supported, support.reasons)
        self.assertEqual(native_build_mode(mir), "mir_go_v1")
        go_source = generate_go_mir_native(mir)
        self.assertIn("type _ksEnumValue struct", go_source)
        self.assertIn('owner: "State", variant: "Ready"', go_source)
        self.assertIn('owner == "State"', go_source)
        self.assertIn('variant == "Ready"', go_source)
        self.assertIn("canonical variant payload proof mismatch", go_source)
        self.assertNotIn("MirAstFallback", go_source)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is required")
    def test_public_build_executes_user_enum_match_from_mir_go(self) -> None:
        source, mir = self.checked_mir(
            """
enum State {
    Ready(Int),
    Idle,
}

fn main() {
    println(match Ready(99) {
        Ready(value) => value,
        Idle => 0,
    })
}
"""
        )
        support = inspect_mir_go_support(mir)
        self.assertTrue(support.supported, support.reasons)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "enum-native"
            with patch.object(
                legacy_cli,
                "command_build",
                side_effect=AssertionError("legacy AST-Go path must not run"),
            ):
                code = cli_main(["build", str(source), "-o", str(target)])
            self.assertEqual(code, 0)
            completed = subprocess.run(
                [str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "99\n")


if __name__ == "__main__":
    unittest.main()
