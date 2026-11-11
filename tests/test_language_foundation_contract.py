from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from koschei.language_foundation_export import (
    LanguageFoundationExportError,
    build_language_foundation_corpus,
    verify_language_foundation_corpus,
    write_language_foundation_corpus,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _head() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class LanguageFoundationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = build_language_foundation_corpus(REPO_ROOT, source_commit=_head())

    def test_unknown_top_level_field_is_rejected(self) -> None:
        payload = copy.deepcopy(self.corpus)
        payload["model_permission"] = "none"
        with self.assertRaisesRegex(LanguageFoundationExportError, "unknown fields"):
            verify_language_foundation_corpus(payload)

    def test_document_tampering_is_rejected(self) -> None:
        payload = copy.deepcopy(self.corpus)
        payload["documents"][0]["text"] += "tampered"
        with self.assertRaisesRegex(LanguageFoundationExportError, "hash mismatch"):
            verify_language_foundation_corpus(payload)

    def test_digest_tampering_is_rejected(self) -> None:
        payload = copy.deepcopy(self.corpus)
        payload["corpus_sha256"] = "f" * 64
        with self.assertRaisesRegex(LanguageFoundationExportError, "digest mismatch"):
            verify_language_foundation_corpus(payload)

    def test_malformed_payload_is_not_published(self) -> None:
        payload = copy.deepcopy(self.corpus)
        payload["documents"][0]["family"] = "example:forged"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "corpus.json"
            with self.assertRaises(LanguageFoundationExportError):
                write_language_foundation_corpus(payload, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
