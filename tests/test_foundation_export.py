from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from koschei.foundation_export import (
    FoundationExportError,
    build_foundation_corpus,
    load_foundation_corpus,
    verify_foundation_corpus,
    write_foundation_corpus,
)


class FoundationExportTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        (root / "docs").mkdir()
        (root / "examples" / "supply_chain").mkdir(parents=True)
        (root / "examples" / "hello").mkdir(parents=True)
        (root / "README.md").write_text("# Koschei\n", encoding="utf-8")
        (root / "README.tr.md").write_text("# Koschei TR\n", encoding="utf-8")
        (root / "docs" / "capabilities.md").write_text("No ambient authority.\n", encoding="utf-8")
        (root / "examples" / "supply_chain" / "main.ks").write_text(
            'import analytics\nfn main() { println("blocked") }\n', encoding="utf-8"
        )
        (root / "examples" / "supply_chain" / "analytics.ks").write_text(
            'fn track() { println("no authority") }\n', encoding="utf-8"
        )
        (root / "examples" / "hello" / "main.ks").write_text(
            'fn main() { println("hello") }\n', encoding="utf-8"
        )
        (root / "examples" / "ignored.txt").write_text("not language material\n", encoding="utf-8")

    def test_build_is_deterministic_and_groups_program_families(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            first = build_foundation_corpus(root, source_commit="a" * 40)
            second = build_foundation_corpus(root, source_commit="a" * 40)
            self.assertEqual(first.corpus_sha256, second.corpus_sha256)
            self.assertEqual(first.document_count, 6)
            supply_chain = [
                item for item in first.documents if item.path.startswith("examples/supply_chain/")
            ]
            self.assertEqual({item.family for item in supply_chain}, {"example:supply_chain"})
            self.assertEqual(
                [item.path for item in first.documents],
                sorted(item.path for item in first.documents),
            )

    def test_tampered_text_is_rejected_even_if_json_is_well_formed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = build_foundation_corpus(root, source_commit="b" * 40)
            payload = corpus.to_dict()
            payload["documents"][0]["text"] += "tampered"
            with self.assertRaisesRegex(FoundationExportError, "source hash mismatch"):
                verify_foundation_corpus(payload)

    def test_write_is_no_replace_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = build_foundation_corpus(root, source_commit="c" * 40)
            output = root / "build" / "foundation.json"
            write_foundation_corpus(corpus, output)
            loaded = load_foundation_corpus(output)
            self.assertEqual(loaded.corpus_sha256, corpus.corpus_sha256)
            with self.assertRaises(FileExistsError):
                write_foundation_corpus(corpus, output)

    def test_unknown_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            payload = build_foundation_corpus(root, source_commit="d" * 40).to_dict()
            payload["surprise"] = True
            with self.assertRaisesRegex(FoundationExportError, "fields do not match"):
                verify_foundation_corpus(payload)

    def test_invalid_commit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            with self.assertRaisesRegex(FoundationExportError, "source_commit"):
                build_foundation_corpus(root, source_commit="main")

    def test_loaded_digest_cannot_be_recomputed_around_tampered_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = build_foundation_corpus(root, source_commit="e" * 40)
            output = root / "corpus.json"
            payload = corpus.to_dict()
            payload["documents"][-1]["family"] = "example:other"
            output.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(FoundationExportError, "family mismatch"):
                load_foundation_corpus(output)


if __name__ == "__main__":
    unittest.main()
