from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from koschei.foundation_export import (
    FoundationExportError,
    build_foundation_corpus,
    canonical_json,
    load_foundation_corpus,
    verify_foundation_corpus,
)


def _make_repo(root: Path) -> None:
    (root / "docs").mkdir()
    (root / "examples" / "hello").mkdir(parents=True)
    (root / "README.md").write_text("# Koschei\n", encoding="utf-8")
    (root / "README.tr.md").write_text("# Koschei TR\n", encoding="utf-8")
    (root / "docs" / "capabilities.md").write_text(
        "No ambient authority.\n",
        encoding="utf-8",
    )
    (root / "examples" / "hello" / "main.ks").write_text(
        'fn main() { println("hello") }\n',
        encoding="utf-8",
    )


def _init_git(root: Path) -> str:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@koschei.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Koschei Tests"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "original"], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _rehash(payload: dict[str, object]) -> None:
    documents = payload["documents"]
    payload["document_count"] = len(documents)
    payload["family_count"] = len({item["family"] for item in documents})
    payload["total_bytes"] = sum(len(item["text"].encode()) for item in documents)
    digest_payload = dict(payload)
    digest_payload.pop("corpus_sha256", None)
    payload["corpus_sha256"] = hashlib.sha256(
        canonical_json(digest_payload).encode()
    ).hexdigest()


class FoundationExportProvenanceTests(unittest.TestCase):
    def test_git_replace_objects_cannot_substitute_pinned_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _make_repo(root)
            original_commit = _init_git(root)
            original_text = (root / "README.md").read_text(encoding="utf-8")

            (root / "README.md").write_text("# replacement bytes\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "replacement"],
                cwd=root,
                check=True,
            )
            replacement_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "checkout", "-q", original_commit],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "replace", original_commit, replacement_commit],
                cwd=root,
                check=True,
            )

            corpus = build_foundation_corpus(root, source_commit=original_commit)
            readme = next(item for item in corpus.documents if item.path == "README.md")
            self.assertEqual(readme.text, original_text)
            self.assertNotEqual(readme.text, "# replacement bytes\n")

    def test_trusted_export_requires_head_to_be_a_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _make_repo(root)
            commit = _init_git(root)
            tree = subprocess.run(
                ["git", "rev-parse", f"{commit}^{{tree}}"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            symbolic_ref = subprocess.run(
                ["git", "symbolic-ref", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "update-ref", symbolic_ref, tree],
                cwd=root,
                check=True,
            )
            with self.assertRaisesRegex(FoundationExportError, "readable commit"):
                build_foundation_corpus(root, source_commit=tree)

    def test_oversized_json_integer_is_a_controlled_verification_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_text(
                '{"document_count":' + ("9" * 5000) + "}",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(FoundationExportError, "not valid JSON"):
                load_foundation_corpus(path)

    def test_deeply_recursive_json_is_a_controlled_verification_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
            with self.assertRaisesRegex(FoundationExportError, "not valid JSON"):
                load_foundation_corpus(path)

    def test_verified_paths_reject_embedded_nul_even_when_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _make_repo(root)
            corpus = build_foundation_corpus(
                root,
                source_commit="a" * 40,
                verify_checkout=False,
            )
            payload = corpus.to_dict()
            changed = payload["documents"][0]
            changed["path"] = "docs/a\x00.md"
            changed["family"] = "reference:docs/a\x00.md"
            changed["document_id"] = hashlib.sha256(
                (
                    f"{changed['kind']}\0{changed['family']}\0{changed['path']}\0"
                    f"{changed['source_sha256']}"
                ).encode()
            ).hexdigest()
            payload["documents"].sort(key=lambda item: item["path"])
            _rehash(payload)
            with self.assertRaisesRegex(
                FoundationExportError,
                "unsafe or non-canonical foundation document path",
            ):
                verify_foundation_corpus(payload)

    def test_verified_paths_reject_noncanonical_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _make_repo(root)
            corpus = build_foundation_corpus(
                root,
                source_commit="c" * 40,
                verify_checkout=False,
            )
            payload = corpus.to_dict()
            changed = next(
                item
                for item in payload["documents"]
                if item["path"] == "docs/capabilities.md"
            )
            changed["path"] = "docs/./capabilities.md"
            changed["family"] = "reference:docs/./capabilities.md"
            changed["document_id"] = hashlib.sha256(
                (
                    f"{changed['kind']}\0{changed['family']}\0{changed['path']}\0"
                    f"{changed['source_sha256']}"
                ).encode()
            ).hexdigest()
            payload["documents"].sort(key=lambda item: item["path"])
            _rehash(payload)
            with self.assertRaisesRegex(
                FoundationExportError,
                "non-canonical foundation document path",
            ):
                verify_foundation_corpus(payload)

    def test_verifier_rejects_document_above_builder_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _make_repo(root)
            corpus = build_foundation_corpus(
                root,
                source_commit="b" * 40,
                verify_checkout=False,
            )
            payload = corpus.to_dict()
            changed = next(
                item
                for item in payload["documents"]
                if item["path"] == "docs/capabilities.md"
            )
            changed["text"] = "x" * (512 * 1024 + 1)
            changed["source_sha256"] = hashlib.sha256(
                changed["text"].encode()
            ).hexdigest()
            changed["document_id"] = hashlib.sha256(
                (
                    f"{changed['kind']}\0{changed['family']}\0{changed['path']}\0"
                    f"{changed['source_sha256']}"
                ).encode()
            ).hexdigest()
            _rehash(payload)
            with self.assertRaisesRegex(
                FoundationExportError,
                "exceeds size limit",
            ):
                verify_foundation_corpus(payload)


if __name__ == "__main__":
    unittest.main()
