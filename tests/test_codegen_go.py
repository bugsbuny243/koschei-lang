from __future__ import annotations

import io
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei.codegen_go import CodegenError, generate_go
from koschei.cli import main
from koschei.parser import parse
from koschei.semantic import SemanticError, check

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GO_BINARY = shutil.which("go")

# Saf programlar ve capability kullanan programlar aynı native backend’den geçer.
PURE_EXAMPLES = ("hello.ks", "control_flow.ks")
CAPABILITY_EXAMPLES = ("capability.ks", "runtime_demo.ks", "showcase.ks")


def compile_source(source: str) -> str:
    program = parse(source)
    check(program)
    return generate_go(program)


class GoCodegenTests(unittest.TestCase):
    def test_pure_examples_produce_go_source(self) -> None:
        for name in PURE_EXAMPLES:
            with self.subTest(example=name):
                source = (REPO_ROOT / "examples" / name).read_text(encoding="utf-8")
                generated = compile_source(source)
                self.assertIn("package main", generated)
                self.assertIn("func ksfn_main() any", generated)
                self.assertIn("func main() {", generated)

    def test_capability_programs_produce_native_runtime_source(self) -> None:
        for name in CAPABILITY_EXAMPLES:
            with self.subTest(example=name):
                source = (REPO_ROOT / "examples" / name).read_text(encoding="utf-8")
                generated = compile_source(source)
                self.assertIn("ksNewSystemCaps", generated)
                self.assertIn("ksCallMethod", generated)

    def test_unscoped_capability_name_is_rejected_semantically(self) -> None:
        source = (
            "fn main() { "
            'let secret = disk.read("/etc/passwd") or "" '
            "}"
        )
        with self.assertRaises(SemanticError) as context:
            check(parse(source))
        self.assertEqual(context.exception.code, "KS2401")

    def test_wrong_arity_is_rejected_with_ks4003(self) -> None:
        source = (
            "fn add(a: Int, b: Int) -> Int { return a + b } "
            "fn main() { let total = add(1) }"
        )
        program = parse(source)
        with self.assertRaises(CodegenError) as context:
            generate_go(program)
        self.assertEqual(context.exception.code, "KS4003")

    def test_identifiers_are_prefixed_to_avoid_go_keywords(self) -> None:
        # 'range', 'func', 'type' Go anahtar kelimeleridir; çakışmamalıdır.
        source = "fn main() { let range = 1 let func = 2 println(range) println(func) }"
        generated = compile_source(source)
        self.assertIn("ksv_range", generated)
        self.assertIn("ksv_func", generated)

    def test_all_three_or_forms_are_translated(self) -> None:
        source = (
            'fn parse_port(raw: String) -> Int or Error { '
            'let port = raw.to_int() or return Error("geçersiz") '
            "return port "
            "} "
            "fn main() { "
            'let a = parse_port("80") or 8080 '
            'let b = parse_port("x") or { println("yedek") } '
            'let c = parse_port("90") or return '
            "}"
        )
        generated = compile_source(source)
        self.assertIn("ksIsError(", generated)
        self.assertGreaterEqual(generated.count("ksIsError("), 3)

    def test_booleans_render_lowercase_like_source(self) -> None:
        generated = compile_source("fn main() { println(true) }")
        self.assertIn("ksPrintln(true)", generated)


    def test_trim_and_expression_interpolation_are_generated(self) -> None:
        generated = compile_source(
            'fn main() { let name = "  Koschei  ".trim() '
            'println("{name}:{1 + 2}") }'
        )
        self.assertIn("ksTrim", generated)
        self.assertIn("ksAdd", generated)

    def test_split_is_fail_closed_until_native_list_runtime(self) -> None:
        with self.assertRaises(CodegenError) as context:
            compile_source('fn main() { let parts = "a,b".split(",") }')
        self.assertEqual(context.exception.code, "KS4002")
        self.assertIn("native List desteği", context.exception.message)


class EmitGoCommandTests(unittest.TestCase):
    def test_emit_go_prints_source(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["emit-go", str(REPO_ROOT / "examples" / "hello.ks")])
        self.assertEqual(exit_code, 0)
        self.assertIn("package main", output.getvalue())


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native derleme testleri atlandı")
class NativeBuildTests(unittest.TestCase):
    """Üretilen binary, yorumlayıcıyla AYNI çıktıyı vermelidir.

    Bu testler yalnızca Go kurulu ortamlarda (ör. CI) çalışır. Native derlemenin
    asıl kabul kapısı budur: davranış eşliği kanıtlanmadan codegen doğru sayılmaz.
    """

    def build_and_run(self, source_path: pathlib.Path) -> str:
        generated = compile_source(source_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="koschei-test-") as workspace:
            directory = pathlib.Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheitest\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "program"
            build = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=directory,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                build.returncode, 0, f"go build başarısız:\n{build.stderr}"
            )
            executed = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            return executed.stdout

    def interpret(self, source_path: pathlib.Path) -> str:
        result = subprocess.run(
            ["python3", "-m", "koschei", "run", str(source_path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_native_output_matches_interpreter(self) -> None:
        for name in PURE_EXAMPLES:
            with self.subTest(example=name):
                path = REPO_ROOT / "examples" / name
                self.assertEqual(self.build_and_run(path), self.interpret(path))

    def test_arithmetic_and_strings_match_interpreter(self) -> None:
        source = (
            "fn main() { "
            "let total = 2 + 3 * 4 "
            'let name = "  koschei  ".trim() '
            "let size = name.length() "
            'let flag = name.contains("osc") '
            'let port = "8080".to_int() or 0 '
            'let fallback = "abc".to_int() or 1234 '
            'println("{total} {size} {flag} {port} {fallback}") '
            "}"
        )
        with tempfile.TemporaryDirectory(prefix="koschei-src-") as workspace:
            path = pathlib.Path(workspace) / "case.ks"
            path.write_text(source, encoding="utf-8")
            self.assertEqual(self.build_and_run(path), self.interpret(path))

    def test_recursion_depth_guard_exists_in_binary(self) -> None:
        source = (
            "fn boom(n: Int) -> Int { return boom(n + 1) } "
            "fn main() { let x = boom(0) }"
        )
        generated = compile_source(source)
        self.assertIn("ksMaxDepth", generated)
        with tempfile.TemporaryDirectory(prefix="koschei-depth-") as workspace:
            directory = pathlib.Path(workspace)
            (directory / "main.go").write_text(generated, encoding="utf-8")
            (directory / "go.mod").write_text(
                "module koscheidepth\n\ngo 1.21\n", encoding="utf-8"
            )
            binary = directory / "program"
            build = subprocess.run(
                [GO_BINARY, "build", "-o", str(binary), "."],
                cwd=directory,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            executed = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(executed.returncode, 1)
            self.assertIn("KS3105", executed.stderr)

    def test_build_command_produces_runnable_binary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-cli-") as workspace:
            target = pathlib.Path(workspace) / "hello"
            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    "koschei",
                    "build",
                    "examples/hello.ks",
                    "-o",
                    str(target),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.exists())
            self.assertTrue(os.access(target, os.X_OK))
            executed = subprocess.run(
                [str(target)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(executed.returncode, 0)
            self.assertIn("Koschei", executed.stdout)


if __name__ == "__main__":
    unittest.main()
