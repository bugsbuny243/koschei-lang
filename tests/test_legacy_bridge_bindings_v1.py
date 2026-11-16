"""Regressions found by Koschei Forms (#400).

1. A Map unwrapped from a List with `or` (`let m = maps.get(i) or { ... }`)
   reached the legacy checker untyped, and `m.get(key)` was refused as a
   capability call (KS2401). Typed HIR knew the type; the bridge now passes it.
2. An error found in an imported module was reported with the name of the
   file that was checked.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from koschei.cli_entry import main as cli_main

UNWRAPPED = '''fn first(records: List<Map<String, String>>) -> String {
    let mut i = 0
    while i < records.length() {
        let fields = records.get(i) or {
            i = i + 1
            continue
        }
        i = i + 1
        return fields.get("x") or ""
    }
    return ""
}

fn second(records: List<Map<String, String>>) -> String {
    let fields = records.get(0) or return ""
    return fields.get("x") or ""
}

fn third(groups: List<List<String>>) -> String {
    let names = groups.get(0) or return ""
    return names.get(0) or ""
}

fn main() {
    let m: Map<String, String> = {"x": "1"}
    println(first([m]) + second([m]) + third([["2"]]))
}
'''

AMBIENT_IN_IMPORT = '''fn broken() -> String {
    let y = disk.read("/etc/passwd") or return ""
    return y
}
'''


def run(arguments: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(arguments)
    return code, out.getvalue(), err.getvalue()


class LegacyBridgeBindingTests(unittest.TestCase):
    def test_unwrapped_map_and_list_elements_keep_their_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.ks"
            path.write_text(UNWRAPPED, encoding="utf-8")
            code, _, errors = run(["--lang", "en", "check", str(path)])
            self.assertEqual(code, 0, errors)
            code, output, errors = run(["run", str(path)])
            self.assertEqual(code, 0, errors)
            self.assertEqual(output, "112\n")

    def test_ambient_authority_is_still_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.ks"
            path.write_text(
                "fn leak(things: List<String>) -> String {\n"
                "    let x = things.get(0) or return \"\"\n"
                "    let y = disk.read(\"/etc/passwd\") or return \"\"\n"
                "    return x + y\n"
                "}\n\nfn main() {\n    println(leak([\"a\"]))\n}\n",
                encoding="utf-8",
            )
            code, _, errors = run(["--lang", "en", "check", str(path)])
            self.assertEqual(code, 1)
            self.assertIn("KS2401", errors)


class ImportedModuleDiagnosticTests(unittest.TestCase):
    def test_error_names_the_imported_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "helper.ks").write_text(AMBIENT_IN_IMPORT, encoding="utf-8")
            (root / "main.ks").write_text(
                "import helper\n\nfn main() {\n    println(helper.broken())\n}\n", encoding="utf-8"
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                code, _, errors = run(["--lang", "en", "check", "main.ks"])
                self.assertEqual(code, 1)
                self.assertTrue(errors.startswith("KOSCHEI ERROR: helper.ks: KS2401 [line 2, column 13]"), errors)
                code, output, _ = run(["--lang", "en", "check", "--json", "main.ks"])
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output)["source"], "helper.ks")
                # An error in the file that was asked for keeps the old text.
                code, _, errors = run(["--lang", "en", "check", "helper.ks"])
                self.assertTrue(errors.startswith("KOSCHEI ERROR: KS2401"), errors)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
