from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei.codegen_go import generate_go
from koschei.interpreter import run
from koschei.parser import parse
from koschei.semantic import check

GO_BINARY = shutil.which("go")
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native algebraic-type testleri atlandı")
class NativeAlgebraicCodegenTests(unittest.TestCase):
    def native_output(self, source: str) -> str:
        program = parse(source)
        check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-adt-")
        self.addCleanup(workspace.cleanup)
        directory = pathlib.Path(workspace.name)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheialgebraic\n\ngo 1.21\n", encoding="utf-8"
        )
        binary = directory / "program"
        built = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=directory,
            capture_output=True,
            text=True,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        completed = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    @staticmethod
    def interpreter_output(source: str) -> str:
        program = parse(source)
        check(program)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run(program, [])
        if code != 0:
            raise AssertionError(f"interpreter exit: {code}")
        return output.getvalue()

    def assert_native_parity(self, source: str) -> None:
        self.assertEqual(self.native_output(source), self.interpreter_output(source))

    def test_v08_showcase_matches_interpreter(self) -> None:
        source = (REPO_ROOT / "examples" / "v08_types.ks").read_text(encoding="utf-8")
        self.assert_native_parity(source)

    def test_nested_match_and_payload_binding(self) -> None:
        source = """
        enum Outer { Empty, Wrapped(Option<String>) }
        fn describe(value: Outer) -> String {
            return match value {
                Empty => "boş",
                Wrapped(option) => match option {
                    Some(text) => text,
                    None => "yok",
                },
            }
        }
        fn main() {
            println(describe(Wrapped(Some("iç"))))
            println(describe(Wrapped(None())))
        }
        """
        self.assert_native_parity(source)

    def test_result_or_return_propagates_err(self) -> None:
        source = """
        fn inner(active: Bool) -> Result<String, Error> {
            if active { return Ok("tamam") }
            return Err(Error("bozuk"))
        }
        fn outer(active: Bool) -> Result<String, Error> {
            let value = inner(active) or return
            return Ok(value)
        }
        fn main() {
            println(match outer(true) { Ok(value) => value, Err(error) => "hata", })
            println(match outer(false) { Ok(value) => value, Err(error) => "taşındı", })
        }
        """
        self.assert_native_parity(source)

    def test_enum_equality_is_structural(self) -> None:
        source = """
        enum State { Empty, Ready(String) }
        fn main() {
            println(Empty() == Empty())
            println(Ready("x") == Ready("x"))
            println(Ready("x") != Ready("y"))
            println(Some("x") == Some("x"))
            println(Err(Error("x")) == Err(Error("x")))
        }
        """
        self.assert_native_parity(source)

    def test_option_or_else_unwraps_some(self) -> None:
        source = """
        fn maybe(active: Bool) -> Option<String> {
            if active { return Some("var") }
            return None()
        }
        fn main() {
            println(maybe(true) or "yok")
            println(maybe(false) or "yok")
        }
        """
        self.assert_native_parity(source)

    def test_native_runtime_rejects_capability_payload_defensively(self) -> None:
        # Semantic checker normalde bunu KS2401 ile reddeder. Runtime savunmasını
        # kanıtlamak için codegen doğrudan AST üzerinde çalıştırılır.
        source = """
        fn main(caps: SystemCaps) {
            let net = caps.net.allow("https://example.com")
            let hidden = Some(net)
            println(hidden)
        }
        """
        generated = generate_go(parse(source))
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-adt-cap-")
        self.addCleanup(workspace.cleanup)
        directory = pathlib.Path(workspace.name)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheialgebraiccap\n\ngo 1.21\n", encoding="utf-8"
        )
        binary = directory / "program"
        built = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=directory,
            capture_output=True,
            text=True,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        completed = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("KS3401", completed.stdout)


if __name__ == "__main__":
    unittest.main()
