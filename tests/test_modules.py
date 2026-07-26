from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import analyze_graph
from koschei.codegen_go import CodegenError, generate_go
from koschei.interpreter import Interpreter
from koschei.cli import main
from koschei.modules import ModuleError, check_graph, load_graph, module_imports, namespaces
from koschei.parser import parse
from koschei.semantic import SemanticError

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"


class ModuleWorkspace(unittest.TestCase):
    """Geçici bir dizinde çok dosyalı program kurar."""

    def workspace(self, files: dict[str, str]) -> pathlib.Path:
        directory = pathlib.Path(tempfile.mkdtemp(prefix="koschei-mod-"))
        self.addCleanup(self._cleanup, directory)
        for name, content in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return directory

    @staticmethod
    def _cleanup(directory: pathlib.Path) -> None:
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        directory.rmdir()

    def run_program(self, directory: pathlib.Path, entry: str) -> str:
        graph = load_graph(directory / entry)
        check_graph(graph)
        root = graph.root_module
        output = io.StringIO()
        with redirect_stdout(output):
            Interpreter(
                root.program,
                [],
                namespaces(graph),
                root.imports,
                module_imports=module_imports(graph),
            ).execute_main()
        return output.getvalue()


class ModuleLoadingTests(ModuleWorkspace):
    def test_missing_module_file_is_reported(self) -> None:
        directory = self.workspace({"main.ks": "import yok\nfn main() { return }\n"})
        with self.assertRaises(ModuleError) as context:
            load_graph(directory / "main.ks")
        self.assertEqual(context.exception.code, "KS1601")

    def test_import_cycle_is_rejected(self) -> None:
        directory = self.workspace(
            {
                "a.ks": "import b\nfn main() { let x = b.f() }\n",
                "b.ks": "import a\nfn f() -> Int { return 1 }\n",
            }
        )
        with self.assertRaises(ModuleError) as context:
            load_graph(directory / "a.ks")
        self.assertEqual(context.exception.code, "KS1602")

    def test_duplicate_import_is_rejected(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import lib\nimport lib\nfn main() { return }\n",
                "lib.ks": "fn f() -> Int { return 1 }\n",
            }
        )
        with self.assertRaises(ModuleError) as context:
            load_graph(directory / "main.ks")
        self.assertEqual(context.exception.code, "KS1603")

    def test_dependencies_come_before_dependents(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import lib\nfn main() { let x = lib.f() }\n",
                "lib.ks": "fn f() -> Int { return 1 }\n",
            }
        )
        graph = load_graph(directory / "main.ks")
        order = [module.path.name for module in graph.in_dependency_order()]
        self.assertEqual(order, ["lib.ks", "main.ks"])


class ModuleSemanticTests(ModuleWorkspace):
    def test_struct_name_collision_is_rejected(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "struct Holder { id: Int }\nimport lib\nfn main() { return }\n",
                "lib.ks": "struct Holder { name: String }\nfn f() -> Int { return 1 }\n",
            }
        )
        with self.assertRaises(SemanticError) as context:
            check_graph(load_graph(directory / "main.ks"))
        self.assertEqual(context.exception.code, "KS1604")

    def test_unknown_module_member_is_rejected(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import lib\nfn main() { let x = lib.missing() }\n",
                "lib.ks": "fn f() -> Int { return 1 }\n",
            }
        )
        with self.assertRaises(SemanticError) as context:
            check_graph(load_graph(directory / "main.ks"))
        self.assertEqual(context.exception.code, "KS1605")

    def test_module_names_are_not_visible_to_the_module_itself(self) -> None:
        # lib, main'in isimlerini göremez: her modül kendi ad alanında denetlenir.
        directory = self.workspace(
            {
                "main.ks": "import lib\nfn helper() -> Int { return 1 }\nfn main() { let x = lib.f() }\n",
                "lib.ks": "fn f() -> Int { return helper() }\n",
            }
        )
        with self.assertRaises(SemanticError) as context:
            check_graph(load_graph(directory / "main.ks"))
        self.assertEqual(context.exception.code, "KS1101")

    def test_fallible_module_call_must_be_handled(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import lib\nfn main() { lib.risky() }\n",
                "lib.ks": 'fn risky() -> Int or Error { return Error("x") }\n',
            }
        )
        with self.assertRaises(SemanticError) as context:
            check_graph(load_graph(directory / "main.ks"))
        self.assertEqual(context.exception.code, "KS1401")


class ImportGrantsNoAuthorityTests(ModuleWorkspace):
    """Dilin merkezi iddiasının çok dosyalı karşılığı."""

    def test_imported_module_cannot_touch_disk_without_a_token(self) -> None:
        directory = self.workspace(
            {
                "main.ks": 'import analytics\nfn main() { let x = analytics.track("c") or "" }\n',
                "analytics.ks": (
                    "fn track(event: String) -> String or Error {\n"
                    '    let secret = disk.read("/etc/app/secrets.env") or return Error("yok")\n'
                    "    return secret\n"
                    "}\n"
                ),
            }
        )
        with self.assertRaises(SemanticError) as context:
            check_graph(load_graph(directory / "main.ks"))
        self.assertEqual(context.exception.code, "KS2401")

    def test_module_may_use_a_capability_that_is_passed_to_it(self) -> None:
        directory = self.workspace(
            {
                "main.ks": (
                    "import store\n"
                    "fn main(caps: SystemCaps) {\n"
                    '    let cfg = caps.disk.allow_read_only("/etc/app/")\n'
                    '    let text = store.load(cfg, "/etc/app/config.json") or "yok"\n'
                    "    println(text)\n"
                    "}\n"
                ),
                "store.ks": (
                    "fn load(disk: DiskReadCaps, path: String) -> String or Error {\n"
                    '    let content = disk.read(path) or return Error("okunamadi")\n'
                    "    return content\n"
                    "}\n"
                ),
            }
        )
        check_graph(load_graph(directory / "main.ks"))

    def test_manifest_covers_imported_modules(self) -> None:
        directory = self.workspace(
            {
                "main.ks": (
                    "import store\n"
                    "fn main(caps: SystemCaps) {\n"
                    '    let cfg = caps.disk.allow_read_only("/etc/app/")\n'
                    '    let text = store.load(cfg, "/etc/app/x") or ""\n'
                    "}\n"
                ),
                "store.ks": (
                    "fn load(disk: DiskReadCaps, path: String) -> String or Error {\n"
                    '    let content = disk.read(path) or return Error("okunamadi")\n'
                    "    return content\n"
                    "}\n"
                ),
            }
        )
        graph = load_graph(directory / "main.ks")
        check_graph(graph)
        manifest = analyze_graph(graph)
        self.assertEqual({grant.domain for grant in manifest.grants}, {"disk"})
        # Yetkiyi TAŞIYAN fonksiyon içe aktarılan modüldedir ve manifestoda görünür.
        self.assertIn("store.load", manifest.holder_functions)


class ModuleRuntimeTests(ModuleWorkspace):
    def test_module_function_is_called_in_its_own_namespace(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import lib\nfn helper() -> Int { return 999 }\nfn main() { println(lib.outer()) }\n",
                "lib.ks": (
                    "fn inner() -> Int { return 7 }\n"
                    "fn outer() -> Int { return inner() }\n"
                ),
            }
        )
        self.assertEqual(self.run_program(directory, "main.ks"), "7\n")

    def test_module_struct_is_usable_in_the_importer(self) -> None:
        directory = self.workspace(
            {
                "main.ks": (
                    "import shapes\n"
                    'fn main() { let b = Box { label: "kutu" } println(shapes.describe(b)) }\n'
                ),
                "shapes.ks": (
                    "struct Box { label: String }\n"
                    "fn describe(box: Box) -> String { return box.label }\n"
                ),
            }
        )
        self.assertEqual(self.run_program(directory, "main.ks"), "kutu\n")


class NativeBackendRejectsImportsTests(unittest.TestCase):
    def test_imports_are_rejected_by_native_backend(self) -> None:
        program = parse("import lib\nfn main() { return }\n")
        with self.assertRaises(CodegenError) as context:
            generate_go(program)
        self.assertEqual(context.exception.code, "KS4002")


class ExampleProgramTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            exit_code = main(argv)
        return exit_code, output.getvalue(), error.getvalue()

    def test_multi_file_example_runs(self) -> None:
        code, output, _ = self.run_cli(["run", str(EXAMPLES / "app.ks")])
        self.assertEqual(code, 0)
        self.assertIn("KRITIK", output)
        self.assertIn("Toplam", output)

    def test_supply_chain_example_does_not_compile(self) -> None:
        code, _, error = self.run_cli(
            ["check", str(EXAMPLES / "supply_chain" / "main.ks")]
        )
        self.assertEqual(code, 1)
        self.assertIn("KS2401", error)

    def test_module_examples_are_canonically_formatted(self) -> None:
        from koschei.formatter import check_source

        for path in (
            EXAMPLES / "app.ks",
            EXAMPLES / "risk.ks",
            EXAMPLES / "supply_chain" / "main.ks",
            EXAMPLES / "supply_chain" / "analytics.ks",
        ):
            with self.subTest(example=path.name):
                self.assertTrue(check_source(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
