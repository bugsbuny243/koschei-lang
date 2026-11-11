from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from koschei.foundation_export import (
    FoundationExportError,
    build_foundation_corpus,
    canonical_json,
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
        (root / "docs" / "capabilities.md").write_text(
            "No ambient authority.\n",
            encoding="utf-8",
        )
        (root / "examples" / "supply_chain" / "main.ks").write_text(
            'import analytics\nfn main() { println("blocked") }\n',
            encoding="utf-8",
        )
        (root / "examples" / "supply_chain" / "analytics.ks").write_text(
            'fn track() { println("no authority") }\n',
            encoding="utf-8",
        )
        (root / "examples" / "hello" / "main.ks").write_text(
            'fn main() { println("hello") }\n',
            encoding="utf-8",
        )
        (root / "examples" / "ignored.txt").write_text(
            "not language material\n",
            encoding="utf-8",
        )

    def build(self, root: Path, commit: str):
        return build_foundation_corpus(
            root,
            source_commit=commit,
            verify_checkout=False,
        )

    def init_git_repo(self, root: Path) -> str:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tests@koschei.invalid"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Koschei Tests"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return head.stdout.strip()

    def rehash_payload(self, payload: dict[str, object]) -> None:
        documents = payload["documents"]
        payload["document_count"] = len(documents)
        payload["family_count"] = len({item["family"] for item in documents})
        payload["total_bytes"] = sum(
            len(item["text"].encode()) for item in documents
        )
        digest_payload = dict(payload)
        digest_payload.pop("corpus_sha256", None)
        payload["corpus_sha256"] = hashlib.sha256(
            canonical_json(digest_payload).encode()
        ).hexdigest()

    def test_build_is_deterministic_and_groups_program_families(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            first = self.build(root, "a" * 40)
            second = self.build(root, "a" * 40)
            self.assertEqual(first.corpus_sha256, second.corpus_sha256)
            self.assertEqual(first.document_count, 6)
            supply_chain = [
                item
                for item in first.documents
                if item.path.startswith("examples/supply_chain/")
            ]
            self.assertEqual(
                {item.family for item in supply_chain},
                {"example:supply_chain"},
            )
            readmes = [
                item for item in first.documents if item.path.startswith("README")
            ]
            self.assertEqual(
                {item.family for item in readmes},
                {"reference:README"},
            )
            self.assertEqual(
                [item.path for item in first.documents],
                sorted(item.path for item in first.documents),
            )

    def test_top_level_imported_examples_share_a_safe_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            (root / "examples" / "app.ks").write_text(
                "import risk\nfn main() { risk.label(1) }\n",
                encoding="utf-8",
            )
            (root / "examples" / "risk.ks").write_text(
                "fn label(value: Int) -> Int { return value }\n",
                encoding="utf-8",
            )
            corpus = self.build(root, "f" * 40)
            top_level = [
                item
                for item in corpus.documents
                if item.path in {"examples/app.ks", "examples/risk.ks"}
            ]
            self.assertEqual(
                {item.family for item in top_level},
                {"example:top-level"},
            )

    def test_trusted_export_requires_a_git_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            with self.assertRaisesRegex(FoundationExportError, "Git checkout"):
                build_foundation_corpus(root, source_commit="a" * 40)

    def test_trusted_export_reads_pinned_blob_despite_assume_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            commit = self.init_git_repo(root)
            original = (root / "README.md").read_text(encoding="utf-8")
            subprocess.run(
                ["git", "update-index", "--assume-unchanged", "README.md"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / "README.md").write_text(
                "# worktree mutation that status may hide\n",
                encoding="utf-8",
            )
            corpus = build_foundation_corpus(root, source_commit=commit)
            readme = next(item for item in corpus.documents if item.path == "README.md")
            self.assertEqual(readme.text, original)

    def test_tampered_text_is_rejected_even_if_json_is_well_formed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = self.build(root, "b" * 40)
            payload = corpus.to_dict()
            payload["documents"][0]["text"] += "tampered"
            with self.assertRaisesRegex(FoundationExportError, "source hash mismatch"):
                verify_foundation_corpus(payload)

    def test_write_is_no_replace_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = self.build(root, "c" * 40)
            output = root / "build" / "foundation.json"
            write_foundation_corpus(corpus, output)
            loaded = load_foundation_corpus(output)
            self.assertEqual(loaded.corpus_sha256, corpus.corpus_sha256)
            with self.assertRaises(FileExistsError):
                write_foundation_corpus(corpus, output)

    def test_failed_directory_sync_removes_published_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = self.build(root, "7" * 40)
            output = root / "build" / "foundation.json"
            with mock.patch(
                "koschei.foundation_export.os.fsync",
                side_effect=[None, OSError("directory sync unsupported")],
            ):
                with self.assertRaises(OSError):
                    write_foundation_corpus(corpus, output)
            self.assertFalse(output.exists())

    def test_non_utf8_artifact_is_a_controlled_verification_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(FoundationExportError, "valid UTF-8"):
                load_foundation_corpus(path)

    def test_escaped_lone_surrogate_is_a_controlled_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            payload = self.build(root, "8" * 40).to_dict()
            payload["documents"][0]["text"] = "\ud800"
            path = root / "surrogate.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(FoundationExportError, "valid UTF-8 text"):
                load_foundation_corpus(path)

    def test_duplicate_json_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_text(
                '{"schema_version":"one","schema_version":"two"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(FoundationExportError, "duplicate JSON"):
                load_foundation_corpus(path)

    def test_empty_corpus_is_rejected_even_with_a_matching_digest(self) -> None:
        payload = {
            "schema_version": "koschei.language-foundation-corpus.v1",
            "generator_version": "koschei-foundation-export/v1",
            "source_repository": "bugsbuny243/koschei-lang",
            "source_commit": "9" * 40,
            "document_count": 0,
            "family_count": 0,
            "total_bytes": 0,
            "documents": [],
        }
        payload["corpus_sha256"] = hashlib.sha256(
            canonical_json(payload).encode()
        ).hexdigest()
        with self.assertRaisesRegex(FoundationExportError, "must contain documents"):
            verify_foundation_corpus(payload)

    def test_verifier_enforces_v1_path_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            payload = self.build(root, "6" * 40).to_dict()
            changed = payload["documents"][0]
            changed["path"] = "pyproject.toml"
            changed["family"] = "reference:pyproject.toml"
            changed["document_id"] = hashlib.sha256(
                (
                    f"{changed['kind']}\0{changed['family']}\0{changed['path']}\0"
                    f"{changed['source_sha256']}"
                ).encode()
            ).hexdigest()
            payload["documents"].sort(key=lambda item: item["path"])
            self.rehash_payload(payload)
            with self.assertRaisesRegex(FoundationExportError, "v1 allowlist"):
                verify_foundation_corpus(payload)

    def test_unknown_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            payload = self.build(root, "d" * 40).to_dict()
            payload["surprise"] = True
            with self.assertRaisesRegex(FoundationExportError, "fields do not match"):
                verify_foundation_corpus(payload)

    def test_invalid_commit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            with self.assertRaisesRegex(FoundationExportError, "source_commit"):
                build_foundation_corpus(
                    root,
                    source_commit="main",
                    verify_checkout=False,
                )

    def test_loaded_digest_cannot_be_recomputed_around_tampered_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            corpus = self.build(root, "e" * 40)
            output = root / "corpus.json"
            payload = corpus.to_dict()
            payload["documents"][-1]["family"] = "example:other"
            output.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(FoundationExportError, "family mismatch"):
                load_foundation_corpus(output)


if __name__ == "__main__":
    unittest.main()
