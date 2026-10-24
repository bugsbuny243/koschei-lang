from __future__ import annotations

import io
import json
import pathlib
import random
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.capabilities import analyze_graph
from koschei.cli_entry import main
from koschei.core_library_v1 import (
    CORE_LIBRARY_MODULES_V1,
    CORE_LIBRARY_ROOT,
    core_library_module,
    describe_core_library,
    is_core_library_path,
    main as core_library_main,
)
from koschei.module_lock import ModuleLockError, build_module_lock
from koschei.modules import ModuleError, check_graph, load_graph

# Alphabet for differential inputs: repeated letters force overlapping
# patterns, and the rest covers line breaks, blanks, escapes and non-ASCII.
_ALPHABET = ("a", "a", "b", "ab", " ", "\t", "\r", "\n", "ç", "{", '"', "\\")


def _literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _string_list(values: list[str]) -> str:
    return "[" + ", ".join(_literal(value) for value in values) + "]"


def _int_list(values: list[int]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def _random_text(rng: random.Random, max_parts: int) -> str:
    return "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(0, max_parts)))


def _reference_strip_suffix(value: str, suffix: str) -> str | None:
    if not value.endswith(suffix):
        return None
    return value[: len(value) - len(suffix)]


def _reference_lines(value: str) -> list[str]:
    if not value:
        return []
    pieces = value.split("\n")
    if pieces[-1] == "":
        pieces.pop()
    return [piece[:-1] if piece.endswith("\r") else piece for piece in pieces]


def _reference_words(value: str) -> list[str]:
    return [word for word in re.split(r"[ \t\r\n]", value) if word]


class CoreLibraryWorkspace(unittest.TestCase):
    def workspace(self, files: dict[str, str]) -> pathlib.Path:
        temporary = tempfile.TemporaryDirectory(prefix="koschei-core-library-")
        self.addCleanup(temporary.cleanup)
        directory = pathlib.Path(temporary.name)
        for name, content in files.items():
            (directory / name).write_text(content, encoding="utf-8")
        return directory

    def run_source(self, source: str) -> str:
        directory = self.workspace({"main.ks": source})
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["run", str(directory / "main.ks")])
        self.assertEqual(code, 0, stderr.getvalue())
        return stdout.getvalue()

    def assert_cases_pass(self, imports: str, checks: list[str]) -> None:
        body = "\n".join(checks)
        source = f"{imports}\n\nfn main() {{\n{body}\n    println(\"DONE {len(checks)}\")\n}}\n"
        self.assertEqual(self.run_source(source), f"DONE {len(checks)}\n")


class CoreLibraryResolutionTests(CoreLibraryWorkspace):
    def test_registry_matches_shipped_sources_exactly(self) -> None:
        shipped = sorted(path.stem for path in CORE_LIBRARY_ROOT.glob("*.ks"))
        self.assertEqual(shipped, sorted(CORE_LIBRARY_MODULES_V1))
        for name in CORE_LIBRARY_MODULES_V1:
            path = core_library_module(name)
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file())
            self.assertTrue(is_core_library_path(path))

    def test_unregistered_names_are_not_library_modules(self) -> None:
        for name in ("risk", "helper", "map", "core_library", "../text"):
            self.assertIsNone(core_library_module(name))

    def test_library_import_resolves_to_shipped_module(self) -> None:
        directory = self.workspace(
            {"main.ks": "import text\n\nfn main() {\n    return\n}\n"}
        )
        graph = load_graph(directory / "main.ks")
        check_graph(graph)
        root = graph.root_module
        self.assertEqual(
            graph.module_of(root.imports["text"]).path,
            core_library_module("text"),
        )
        # text imports list from inside the library, never from the project.
        text_module = graph.module_of(root.imports["text"])
        self.assertEqual(
            graph.module_of(text_module.imports["list"]).path,
            core_library_module("list"),
        )

    def test_project_file_with_library_name_fails_closed(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import text\n\nfn main() {\n    return\n}\n",
                "text.ks": "fn starts_with(value: String, prefix: String) -> Bool {\n"
                "    return true\n}\n",
            }
        )
        with self.assertRaises(ModuleError) as caught:
            load_graph(directory / "main.ks")
        self.assertEqual(caught.exception.code, "KS1601")
        self.assertIn("Gölgeleme", caught.exception.message)

    def test_ordinary_sibling_imports_are_unchanged(self) -> None:
        directory = self.workspace(
            {
                "main.ks": "import helper\n\nfn main() {\n    println(helper.name())\n}\n",
                "helper.ks": 'fn name() -> String {\n    return "yerel"\n}\n',
            }
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["run", str(directory / "main.ks")])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "yerel\n")

    def test_library_modules_import_only_library_modules(self) -> None:
        for module in describe_core_library():
            for imported in module.imports:
                self.assertIn(imported, CORE_LIBRARY_MODULES_V1, module.name)

    def test_library_carries_no_capability(self) -> None:
        directory = self.workspace(
            {"main.ks": "import text\nimport list\n\nfn main() {\n    return\n}\n"}
        )
        graph = load_graph(directory / "main.ks")
        check_graph(graph)
        report = analyze_graph(graph)
        self.assertFalse(report.has_any)

    def test_lock_rejects_library_modules_with_clear_reason(self) -> None:
        directory = self.workspace(
            {"main.ks": "import text\n\nfn main() {\n    return\n}\n"}
        )
        with self.assertRaises(ModuleLockError) as caught:
            build_module_lock(directory / "main.ks")
        self.assertEqual(caught.exception.code, "KS1902")
        self.assertIn("Core Library", caught.exception.message)

    def test_describe_reports_public_surface(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(core_library_main(["--json"]), 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], "koschei.core-library/v1")
        surface = {
            module["name"]: {function["name"] for function in module["functions"]}
            for module in payload["modules"]
        }
        self.assertTrue({"starts_with", "ends_with", "replace", "lines"} <= surface["text"])
        self.assertTrue({"first", "last", "reverse", "slice"} <= surface["list"])
        for module in payload["modules"]:
            self.assertRegex(module["sha256"], r"^[0-9a-f]{64}$")


class CoreLibraryTextDifferentialTests(CoreLibraryWorkspace):
    """Each case embeds the Python reference answer in a Koschei program."""

    def test_prefix_and_suffix_operations_match_reference(self) -> None:
        rng = random.Random(20261024)
        checks: list[str] = []
        fixed = [("aaa", "aa"), ("abab", "aba"), ("aabaa", "aa"), ("", ""), ("", "a"), ("a", "")]
        pairs = fixed + [
            (_random_text(rng, 8), _random_text(rng, 3)) for _ in range(140)
        ]
        for index, (value, pattern) in enumerate(pairs):
            v, p = _literal(value), _literal(pattern)
            stripped_suffix = _reference_strip_suffix(value, pattern)
            stripped_prefix = value[len(pattern):] if value.startswith(pattern) else None
            checks.append(
                f"    if text.starts_with({v}, {p}) != {str(value.startswith(pattern)).lower()} {{\n"
                f"        println(\"FAIL starts_with {index}\")\n    }}\n"
                f"    if text.ends_with({v}, {p}) != {str(value.endswith(pattern)).lower()} {{\n"
                f"        println(\"FAIL ends_with {index}\")\n    }}\n"
                f"    let suffix_{index} = text.strip_suffix({v}, {p}) or \"<none>\"\n"
                f"    if suffix_{index} != {_literal('<none>' if stripped_suffix is None else stripped_suffix)} {{\n"
                f"        println(\"FAIL strip_suffix {index}\")\n    }}\n"
                f"    let prefix_{index} = text.strip_prefix({v}, {p}) or \"<none>\"\n"
                f"    if prefix_{index} != {_literal('<none>' if stripped_prefix is None else stripped_prefix)} {{\n"
                f"        println(\"FAIL strip_prefix {index}\")\n    }}"
            )
        self.assert_cases_pass("import text", checks)

    def test_search_and_replace_operations_match_reference(self) -> None:
        rng = random.Random(1024)
        checks: list[str] = []
        triples = [("banana", "an", "+"), ("aaaa", "aa", "b"), ("x", "", "y")] + [
            (_random_text(rng, 8), _random_text(rng, 2), _random_text(rng, 2))
            for _ in range(140)
        ]
        for index, (value, needle, replacement) in enumerate(triples):
            v, n, r = _literal(value), _literal(needle), _literal(replacement)
            if needle:
                expected_before = value.split(needle, 1)[0] if needle in value else "<none>"
                expected_after = value.split(needle, 1)[1] if needle in value else "<none>"
                expected_count = value.count(needle)
                expected_replace = value.replace(needle, replacement)
            else:
                expected_before = expected_after = "<none>"
                expected_count = -1
                expected_replace = "<error>"
            checks.append(
                f"    let before_{index} = text.before({v}, {n}) or \"<none>\"\n"
                f"    if before_{index} != {_literal(expected_before)} {{\n"
                f"        println(\"FAIL before {index}\")\n    }}\n"
                f"    let after_{index} = text.after({v}, {n}) or \"<none>\"\n"
                f"    if after_{index} != {_literal(expected_after)} {{\n"
                f"        println(\"FAIL after {index}\")\n    }}\n"
                f"    let count_{index} = text.count({v}, {n}) or -1\n"
                f"    if count_{index} != {expected_count} {{\n"
                f"        println(\"FAIL count {index}\")\n    }}\n"
                f"    let replace_{index} = text.replace({v}, {n}, {r}) or \"<error>\"\n"
                f"    if replace_{index} != {_literal(expected_replace)} {{\n"
                f"        println(\"FAIL replace {index}\")\n    }}"
            )
        self.assert_cases_pass("import text", checks)

    def test_lines_words_and_blank_checks_match_reference(self) -> None:
        rng = random.Random(77)
        checks: list[str] = []
        values = ["", "\n", "a\r\nb\n", "a\n\nb", " \t "] + [
            _random_text(rng, 10) for _ in range(140)
        ]
        for index, value in enumerate(values):
            v = _literal(value)
            checks.append(
                f"    let expected_lines_{index}: List<String> = {_string_list(_reference_lines(value))}\n"
                f"    if text.lines({v}) != expected_lines_{index} {{\n"
                f"        println(\"FAIL lines {index}\")\n    }}\n"
                f"    let expected_words_{index}: List<String> = {_string_list(_reference_words(value))}\n"
                f"    if text.words({v}) != expected_words_{index} {{\n"
                f"        println(\"FAIL words {index}\")\n    }}\n"
                f"    if text.is_empty({v}) != {str(value == '').lower()} {{\n"
                f"        println(\"FAIL is_empty {index}\")\n    }}\n"
                f"    if text.is_blank({v}) != {str(value.strip() == '').lower()} {{\n"
                f"        println(\"FAIL is_blank {index}\")\n    }}"
            )
        self.assert_cases_pass("import text", checks)


class CoreLibraryListDifferentialTests(CoreLibraryWorkspace):
    def test_list_operations_match_reference(self) -> None:
        rng = random.Random(4242)
        checks: list[str] = []
        for index in range(120):
            items = [rng.randint(-5, 5) for _ in range(rng.randint(0, 6))]
            other = [rng.randint(-5, 5) for _ in range(rng.randint(0, 3))]
            count = rng.randint(-2, 8)
            start = rng.randint(-1, 7)
            end = rng.randint(-1, 7)
            position = rng.randint(-1, 7)
            value = rng.randint(10, 20)

            def expected(result: list[int] | None) -> str:
                return _int_list([] if result is None else result)

            slice_ok = 0 <= start <= end <= len(items)
            insert_ok = 0 <= position <= len(items)
            remove_ok = 0 <= position < len(items)
            first = items[0] if items else -100
            last = items[-1] if items else -100
            checks.append(
                f"    let items_{index}: List<Int> = {_int_list(items)}\n"
                f"    let other_{index}: List<Int> = {_int_list(other)}\n"
                f"    let empty_{index}: List<Int> = []\n"
                f"    if list.is_empty(items_{index}) != {str(not items).lower()} {{\n"
                f"        println(\"FAIL is_empty {index}\")\n    }}\n"
                f"    let first_{index} = list.first(items_{index}) or -100\n"
                f"    if first_{index} != {first} {{\n"
                f"        println(\"FAIL first {index}\")\n    }}\n"
                f"    let last_{index} = list.last(items_{index}) or -100\n"
                f"    if last_{index} != {last} {{\n"
                f"        println(\"FAIL last {index}\")\n    }}\n"
                f"    let concat_expected_{index}: List<Int> = {_int_list(items + other)}\n"
                f"    if list.concat(items_{index}, other_{index}) != concat_expected_{index} {{\n"
                f"        println(\"FAIL concat {index}\")\n    }}\n"
                f"    let reverse_expected_{index}: List<Int> = {_int_list(items[::-1])}\n"
                f"    if list.reverse(items_{index}) != reverse_expected_{index} {{\n"
                f"        println(\"FAIL reverse {index}\")\n    }}\n"
                f"    let drop_expected_{index}: List<Int> = {_int_list(items[max(count, 0):])}\n"
                f"    if list.drop(items_{index}, {count}) != drop_expected_{index} {{\n"
                f"        println(\"FAIL drop {index}\")\n    }}\n"
                f"    let slice_{index} = list.slice(items_{index}, {start}, {end}) or empty_{index}\n"
                f"    let slice_expected_{index}: List<Int> = {expected(items[start:end] if slice_ok else None)}\n"
                f"    if slice_{index} != slice_expected_{index} {{\n"
                f"        println(\"FAIL slice {index}\")\n    }}\n"
                f"    let insert_{index} = list.insert_at(items_{index}, {position}, {value}) or empty_{index}\n"
                f"    let insert_expected_{index}: List<Int> = {expected(items[:position] + [value] + items[position:] if insert_ok else None)}\n"
                f"    if insert_{index} != insert_expected_{index} {{\n"
                f"        println(\"FAIL insert_at {index}\")\n    }}\n"
                f"    let remove_{index} = list.remove_at(items_{index}, {position}) or empty_{index}\n"
                f"    let remove_expected_{index}: List<Int> = {expected(items[:position] + items[position + 1:] if remove_ok else None)}\n"
                f"    if remove_{index} != remove_expected_{index} {{\n"
                f"        println(\"FAIL remove_at {index}\")\n    }}\n"
                f"    let replace_{index} = list.replace_at(items_{index}, {position}, {value}) or empty_{index}\n"
                f"    let replace_expected_{index}: List<Int> = {expected(items[:position] + [value] + items[position + 1:] if remove_ok else None)}\n"
                f"    if replace_{index} != replace_expected_{index} {{\n"
                f"        println(\"FAIL replace_at {index}\")\n    }}"
            )
        self.assert_cases_pass("import list", checks)

    def test_generic_functions_work_for_text_items(self) -> None:
        output = self.run_source(
            "import list\n\nfn main() {\n"
            '    let names = ["ayşe", "ali", "veli"]\n'
            '    let first = list.first(names) or "yok"\n'
            '    let last = list.last(names) or "yok"\n'
            "    println(\"{first} {last} {list.reverse(names)}\")\n"
            "}\n"
        )
        self.assertEqual(output, 'ayşe veli ["veli", "ali", "ayşe"]\n')


if __name__ == "__main__":
    unittest.main()
