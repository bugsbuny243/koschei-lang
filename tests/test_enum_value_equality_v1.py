from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.cli_entry import main
from koschei.interpreter import EnumValue


class EnumValueEqualityTests(unittest.TestCase):
    """Runtime type evidence must not change Koschei structural equality."""

    def test_type_evidence_does_not_take_part_in_equality_or_hash(self) -> None:
        plain = EnumValue("Option", "Some", 1)
        concrete = EnumValue("Option", "Some", 1, ("Int",))
        generic = EnumValue("Option", "Some", 1, ("T",))
        self.assertEqual(plain, concrete)
        self.assertEqual(concrete, generic)
        self.assertEqual(hash(plain), hash(generic))
        self.assertNotEqual(plain, EnumValue("Option", "Some", 2, ("Int",)))
        self.assertNotEqual(plain, EnumValue("Option", "None", type_arguments=("Int",)))

    def test_values_built_at_different_sites_compare_equal(self) -> None:
        source = (
            "import list\n\n"
            "fn main() {\n"
            "    let values = [1, 2]\n"
            "    let missing: Option<Int> = None()\n"
            "    let from_get = values.get(0)\n"
            "    let from_literal = Some(1)\n"
            "    let from_generic = list.first(values)\n"
            "    println(\"{from_get == from_literal} {from_literal == from_generic}\")\n"
            "    println(\"{values.get(9) == missing} {from_get != Some(2)}\")\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory(prefix="koschei-enum-eq-") as directory:
            path = pathlib.Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["run", str(path)])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "true true\ntrue true\n")


if __name__ == "__main__":
    unittest.main()
