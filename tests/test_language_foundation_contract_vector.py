from __future__ import annotations

import json
from pathlib import Path
import unittest

from koschei.language_foundation_export import verify_language_foundation_corpus


REPO_ROOT = Path(__file__).resolve().parents[1]
VECTOR = REPO_ROOT / "fixtures" / "model_training" / "language-foundation-contract-vector.v1.json"
EXPECTED_CORPUS_SHA256 = "873e609284da5e8834bf103659ae42b90cee27710d11d4bc0ad6136200151144"


class LanguageFoundationContractVectorTests(unittest.TestCase):
    def test_shared_vector_is_valid_and_digest_locked(self) -> None:
        payload = json.loads(VECTOR.read_text(encoding="utf-8"))
        verified = verify_language_foundation_corpus(payload)
        self.assertEqual(verified["corpus_sha256"], EXPECTED_CORPUS_SHA256)
        self.assertEqual(verified["document_count"], 6)
        self.assertEqual(verified["family_count"], 5)


if __name__ == "__main__":
    unittest.main()
