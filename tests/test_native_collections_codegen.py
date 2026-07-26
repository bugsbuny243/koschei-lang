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


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native koleksiyon testleri atlandı")
class NativeCollectionsCodegenTests(unittest.TestCase):
    def native_output(self, source: str, *, check_semantics: bool = True) -> str:
        program = parse(source)
        if check_semantics:
            check(program)
        generated = generate_go(program)
        workspace = tempfile.TemporaryDirectory(prefix="koschei-native-collections-")
        self.addCleanup(workspace.cleanup)
        directory = pathlib.Path(workspace.name)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheicollections\n\ngo 1.21\n", encoding="utf-8"
        )
        binary = directory / "program"
        built = subprocess.run(
            [GO_BINARY, "build", "-o", str(binary), "."],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=180,
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

    def test_daily_example_matches_interpreter(self) -> None:
        source = (REPO_ROOT / "examples" / "daily.ks").read_text(encoding="utf-8")
        self.assert_native_parity(source)

    def test_maps_example_matches_interpreter(self) -> None:
        source = (REPO_ROOT / "examples" / "maps.ks").read_text(encoding="utf-8")
        self.assert_native_parity(source)

    def test_list_methods_for_loop_and_immutability(self) -> None:
        source = """
        fn positive(value: Int) -> Bool {
            return value > 0
        }
        fn main() {
            let base = [3, -1, 2]
            let pushed = base.push(4) or []
            let selected = pushed.filter(positive) or []
            let ordered = selected.sort() or []
            let mut total = 0
            for value in ordered {
                total = total + value
            }
            println(base)
            println(pushed)
            println(ordered)
            println(total)
            println(ordered.get(99) or -1)
            println(ordered.contains(3))
        }
        """
        self.assert_native_parity(source)

    def test_string_split_join_and_error_fallbacks(self) -> None:
        source = """
        fn main() {
            let parts = "ali,ayşe,mehmet".split(",")
            println(" | ".join(parts) or "hata")
            println("abc".split("") or [])
            println("-".join(["a", "b", "c"]) or "hata")
        }
        """
        self.assert_native_parity(source)

    def test_map_order_set_equality_and_nested_values(self) -> None:
        source = """
        fn main() {
            let original = {"a": 1, "b": 2}
            let changed = original.set("a", 9).set("c", [3, 4])
            let same = {"a": 9, "b": 2, "c": [3, 4]}
            println(original)
            println(changed)
            println(changed.keys())
            println(changed.get("missing") or "yok")
            println(changed == same)
            println(original.contains("c"))
        }
        """
        self.assert_native_parity(source)

    def test_native_runtime_rejects_capability_inside_list_and_map(self) -> None:
        # Semantic checker normalde her iki yolu da KS2401 ile kapatır. Runtime
        # savunmasını kanıtlamak için codegen doğrudan AST üzerinde çalıştırılır.
        source = """
        fn main(caps: SystemCaps) {
            let net = caps.net.allow("https://example.com")
            println([net])
            println({"hidden": net})
        }
        """
        output = self.native_output(source, check_semantics=False)
        self.assertEqual(output.count("KS3401"), 2)


if __name__ == "__main__":
    unittest.main()
