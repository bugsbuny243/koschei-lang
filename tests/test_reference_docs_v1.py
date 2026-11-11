"""Generated references match the sources they are generated from."""
from __future__ import annotations

import unittest

from koschei.diagnostics import CATALOG
from koschei.reference_docs_v1 import CORE_LIBRARY_PATH, ERROR_CODES_PATH, main


class ReferenceDocsTests(unittest.TestCase):
    def test_committed_references_are_current(self) -> None:
        self.assertEqual(main(["--check"]), 0, "run: python -m koschei.reference_docs_v1 --write")

    def test_every_code_and_module_is_documented(self) -> None:
        errors = ERROR_CODES_PATH.read_text(encoding="utf-8")
        for code in CATALOG:
            self.assertIn(f"### {code} — ", errors)
        library = CORE_LIBRARY_PATH.read_text(encoding="utf-8")
        for name in ("text.starts_with", "list.reverse", "secure.digest", "morag.check", "xandar.check"):
            self.assertIn(f"### `{name}`", library)


if __name__ == "__main__":
    unittest.main()
