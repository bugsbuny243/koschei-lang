from __future__ import annotations

import unittest
from pathlib import Path

from koschei.foreign_contract import load_foreign_contract


class ForeignExampleTests(unittest.TestCase):
    def test_repository_example_artifact_remains_sealed(self):
        root = Path(__file__).resolve().parents[1]
        contract = load_foreign_contract(
            root / "examples" / "interop" / "text_tools.foreign.json"
        )
        self.assertEqual(contract.module, "text.tools")
        self.assertEqual(contract.language, "python")
        self.assertEqual(contract.isolation, "process")
        self.assertEqual(contract.functions, 1)
        self.assertEqual(
            contract.artifact_sha256,
            "40b6a86bee0dab23f1c621d15cdb03a12203a6de14f3b5d7b59302df9d7140fe",
        )


if __name__ == "__main__":
    unittest.main()
