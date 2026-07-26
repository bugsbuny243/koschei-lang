from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from koschei.codegen_go import generate_go
from koschei.cli import main
from koschei.modules import check_graph, load_graph

GO_BINARY = shutil.which("go")
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipUnless(GO_BINARY, "Go kurulu değil; native modül testleri atlandı")
class NativeModulesCodegenTests(unittest.TestCase):
    def workspace(self, files: dict[str, str]) -> pathlib.Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-native-modules-")
        self.addCleanup(temporary.cleanup)
        directory = pathlib.Path(temporary.name)
        for name, source in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return directory

    def native_output(self, path: pathlib.Path) -> str:
        graph = load_graph(path)
        check_graph(graph)
        generated = generate_go(graph.root_module.program, graph)
        directory = path.parent / ".native-test"
        directory.mkdir(exist_ok=True)
        (directory / "main.go").write_text(generated, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheimodules\n\ngo 1.21\n", encoding="utf-8"
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
    def interpreter_output(path: pathlib.Path) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["run", str(path)])
        if code != 0:
            raise AssertionError(f"interpreter exit: {code}")
        return output.getvalue()

    def assert_native_parity(self, path: pathlib.Path) -> None:
        self.assertEqual(self.native_output(path), self.interpreter_output(path))

    def test_app_example_matches_interpreter(self) -> None:
        self.assert_native_parity(REPO_ROOT / "examples" / "app.ks")

    def test_nested_imports_and_local_function_names_are_isolated(self) -> None:
        directory = self.workspace(
            {
                "main.ks": (
                    "import lib\n"
                    "fn helper() -> Int { return 999 }\n"
                    "fn main() { println(lib.outer()) println(helper()) }\n"
                ),
                "lib.ks": (
                    "import util\n"
                    "fn helper() -> Int { return 7 }\n"
                    "fn outer() -> Int { return helper() + util.helper() }\n"
                ),
                "util.ks": "fn helper() -> Int { return 5 }\n",
            }
        )
        self.assert_native_parity(directory / "main.ks")

    def test_imported_struct_and_enum_cross_module_boundary(self) -> None:
        directory = self.workspace(
            {
                "main.ks": (
                    "import model\n"
                    "fn main() {\n"
                    '  let box = Box { label: "kutu" }\n'
                    "  let state = model.wrap(box)\n"
                    "  println(match state { Ready(value) => value.label, Empty => \"boş\", })\n"
                    "}\n"
                ),
                "model.ks": (
                    "struct Box { label: String }\n"
                    "enum State { Empty, Ready(Box) }\n"
                    "fn wrap(box: Box) -> State { return Ready(box) }\n"
                ),
            }
        )
        self.assert_native_parity(directory / "main.ks")

    def test_cli_build_multi_file_program(self) -> None:
        path = REPO_ROOT / "examples" / "app.ks"
        temporary = tempfile.TemporaryDirectory(prefix="koschei-cli-native-module-")
        self.addCleanup(temporary.cleanup)
        binary = pathlib.Path(temporary.name) / "app"
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["build", str(path), "-o", str(binary)])
        self.assertEqual(code, 0, output.getvalue())
        completed = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Toplam", completed.stdout)


if __name__ == "__main__":
    unittest.main()
