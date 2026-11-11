from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from koschei.language_foundation_export import (
    LanguageFoundationExportError,
    verify_language_foundation_corpus,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "model_training"
    / "language-foundation-contract-vector.v1.json"
)


class LanguageFoundationLangBoundaryV1Tests(unittest.TestCase):
    def _vector(self) -> dict[str, object]:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_existing_lang_only_contract_vector_remains_valid(self):
        vector = self._vector()
        self.assertEqual(verify_language_foundation_corpus(vector), vector)

    def test_retired_sentinel_path_is_rejected_before_hash_relabeling(self):
        vector = copy.deepcopy(self._vector())
        documents = vector["documents"]
        self.assertIsInstance(documents, list)
        documents[2]["path"] = "docs/matrix/sentinel-defense-authority-v1.md"

        with self.assertRaisesRegex(
            LanguageFoundationExportError,
            "outside the active Lang corpus boundary",
        ):
            verify_language_foundation_corpus(vector)


if __name__ == "__main__":
    unittest.main()
