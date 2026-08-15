from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from koschei.language_foundation_export import build_language_foundation_corpus


REPO_ROOT = Path(__file__).resolve().parents[1]


class CheckedInLanguageFoundationExportTests(unittest.TestCase):
    def test_checked_in_repository_exports_model_contract_and_financial_reference(self) -> None:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = result.stdout.strip()

        corpus = build_language_foundation_corpus(REPO_ROOT, source_commit=commit)
        paths = {item["path"] for item in corpus["documents"]}
        self.assertIn("docs/MODEL_TRAINING_CONTRACT.md", paths)
        self.assertIn("examples/financial_exchange/matching.ks", paths)
        self.assertIn("examples/financial_exchange/decimal_v1.ks", paths)
        self.assertIn("examples/financial_exchange/order_book_v1.ks", paths)
        self.assertGreater(corpus["document_count"], 10)
        self.assertGreaterEqual(corpus["family_count"], 3)
        self.assertEqual(corpus["source_commit"], commit)


if __name__ == "__main__":
    unittest.main()
