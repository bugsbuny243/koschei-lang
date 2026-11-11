from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from koschei.language_foundation_export import (
    GENERATOR_VERSION,
    SOURCE_REPOSITORY,
    SOURCE_SCHEMA,
    LanguageFoundationExportError,
    build_language_foundation_corpus,
    canonical_json,
    write_language_foundation_corpus,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_repository(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.name", "Koschei Test")
    _git(root, "config", "user.email", "koschei@example.invalid")
    _write(root, "README.md", "# Koschei\n")
    _write(root, "README.tr.md", "# Koschei TR\n")
    _write(root, "docs/types.md", "# Types\nOption and Result.\n")
    _write(root, "docs/types.tr.md", "# Tipler\nOption ve Result.\n")
    _write(root, "examples/app.ks", 'fn main() { println("top") }\n')
    _write(root, "examples/hello/main.ks", 'fn main() { println("hello") }\n')
    _write(root, "examples/hello/helper.ks", "fn answer() -> Int { return 42 }\n")
    _write(root, "examples/supply/main.ks", 'fn main() { println("supply") }\n')
    _write(root, "notes.txt", "must not enter the model corpus\n")
    _write(root, "src/compiler.py", "# implementation is not a syntax template\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


class LanguageFoundationExportTests(unittest.TestCase):
    def test_export_matches_sentinel_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = _fixture_repository(root)
            corpus = build_language_foundation_corpus(root, source_commit=commit)

            self.assertEqual(corpus["schema_version"], SOURCE_SCHEMA)
            self.assertEqual(corpus["generator_version"], GENERATOR_VERSION)
            self.assertEqual(corpus["source_repository"], SOURCE_REPOSITORY)
            self.assertEqual(corpus["source_commit"], commit)
            paths = [item["path"] for item in corpus["documents"]]
            self.assertEqual(paths, sorted(paths))
            self.assertNotIn("notes.txt", paths)
            self.assertNotIn("src/compiler.py", paths)
            self.assertEqual(corpus["document_count"], len(paths))
            self.assertEqual(
                corpus["family_count"],
                len({item["family"] for item in corpus["documents"]}),
            )
            self.assertEqual(
                corpus["total_bytes"],
                sum(len(item["text"].encode()) for item in corpus["documents"]),
            )

            by_path = {item["path"]: item for item in corpus["documents"]}
            self.assertEqual(by_path["README.md"]["family"], "reference:README")
            self.assertEqual(by_path["README.tr.md"]["family"], "reference:README")
            self.assertEqual(
                by_path["docs/types.tr.md"]["family"], "reference:docs/types.md"
            )
            self.assertEqual(by_path["examples/app.ks"]["family"], "example:top-level")
            self.assertEqual(
                by_path["examples/hello/main.ks"]["family"], "example:hello"
            )
            for document in corpus["documents"]:
                source_sha = hashlib.sha256(document["text"].encode()).hexdigest()
                self.assertEqual(document["source_sha256"], source_sha)
                material = (
                    f"{document['kind']}\0{document['family']}\0{document['path']}\0{source_sha}"
                )
                self.assertEqual(
                    document["document_id"], hashlib.sha256(material.encode()).hexdigest()
                )

            digest_payload = dict(corpus)
            observed_digest = digest_payload.pop("corpus_sha256")
            self.assertEqual(
                observed_digest,
                hashlib.sha256(canonical_json(digest_payload).encode()).hexdigest(),
            )

    def test_dirty_and_untracked_worktree_cannot_change_pinned_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = _fixture_repository(root)
            before = build_language_foundation_corpus(root, source_commit=commit)

            _write(root, "README.md", "TAMPERED WORKTREE\n")
            _write(root, "examples/dirty.ks", 'fn main() { println("untracked") }\n')
            after = build_language_foundation_corpus(root, source_commit=commit)

            self.assertEqual(before, after)
            readme = next(item for item in after["documents"] if item["path"] == "README.md")
            self.assertEqual(readme["text"], "# Koschei\n")
            self.assertNotIn(
                "examples/dirty.ks", {item["path"] for item in after["documents"]}
            )

    def test_export_and_serialization_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = _fixture_repository(root)
            first = build_language_foundation_corpus(root, source_commit=commit)
            second = build_language_foundation_corpus(root, source_commit=commit)
            self.assertEqual(first, second)

            first_path = root / "out" / "first.json"
            second_path = root / "out" / "second.json"
            write_language_foundation_corpus(first, first_path)
            write_language_foundation_corpus(second, second_path)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(json.loads(first_path.read_text(encoding="utf-8")), first)

    def test_output_is_no_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = _fixture_repository(root)
            corpus = build_language_foundation_corpus(root, source_commit=commit)
            output = root / "corpus.json"
            write_language_foundation_corpus(corpus, output)
            original = output.read_bytes()
            with self.assertRaises(FileExistsError):
                write_language_foundation_corpus(corpus, output)
            self.assertEqual(output.read_bytes(), original)

    def test_mutable_or_abbreviated_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = _fixture_repository(root)
            for revision in ("main", "HEAD", commit[:12], commit.upper()):
                with self.subTest(revision=revision):
                    with self.assertRaises(LanguageFoundationExportError):
                        build_language_foundation_corpus(root, source_commit=revision)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_selected_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = _fixture_repository(root)
            del commit
            link = root / "docs" / "linked.md"
            try:
                os.symlink("types.md", link)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            _git(root, "add", "docs/linked.md")
            _git(root, "commit", "-m", "add selected symlink")
            symlink_commit = _git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(
                LanguageFoundationExportError, "not a regular tracked file"
            ):
                build_language_foundation_corpus(root, source_commit=symlink_commit)


if __name__ == "__main__":
    unittest.main()
