"""Every package in registry/ is intact, and its listed surface is what the compiler computes.

This runs on every pull request, so a publish PR whose archive, digest or
surface does not match cannot be merged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from koschei.packages_v1 import sync, tree_digest
from koschei.registry_v1 import (
    LOG_NAME,
    archive_path,
    check_log,
    check_signature,
    extract_archive,
    parse_log,
    validate_index,
)

REGISTRY = Path(__file__).resolve().parent.parent / "registry"


def _entries():
    for index_file in sorted((REGISTRY / "index").glob("*.json")):
        name = index_file.stem
        index = validate_index(json.loads(index_file.read_text(encoding="utf-8")), name)
        for entry in index["versions"]:
            yield name, entry


class RegistryContentsTests(unittest.TestCase):
    def test_every_archive_matches_its_index_entry(self) -> None:
        for name, entry in _entries():
            with self.subTest(package=f"{name} {entry['version']}"):
                data = (REGISTRY / archive_path(name, entry["version"])).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["archive_sha256"])
                with tempfile.TemporaryDirectory() as directory:
                    extract_archive(data, Path(directory))
                    self.assertEqual(tree_digest(Path(directory)), entry["digest"])

    def test_every_listed_surface_is_the_computed_one(self) -> None:
        for name, entry in _entries():
            with self.subTest(package=f"{name} {entry['version']}"), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                (project / "koschei.toml").write_text(
                    '[package]\nname = "registry-check"\nversion = "0.0.0"\n\n'
                    f'[registry]\nurl = "file://{REGISTRY}"\n\n'
                    f'[dependencies]\n{name} = {{ version = "{entry["version"]}" }}\n'
                )
                result = sync(project)
                self.assertEqual(list(result.lock.packages[name]["surface"]), entry["surface"])

    def test_public_log_is_a_valid_chain_and_matches_every_entry(self) -> None:
        events = parse_log((REGISTRY / LOG_NAME).read_bytes())
        for name, entry in _entries():
            with self.subTest(package=f"{name} {entry['version']}"):
                check_log(events, name, entry, None)

    def test_signatures_verify_and_signers_are_owners(self) -> None:
        for index_file in sorted((REGISTRY / "index").glob("*.json")):
            name = index_file.stem
            index = validate_index(json.loads(index_file.read_text(encoding="utf-8")), name)
            for entry in index["versions"]:
                with self.subTest(package=f"{name} {entry['version']}"):
                    check_signature(name, entry, index.get("owners", []))

    def test_no_stray_files(self) -> None:
        listed = {archive_path(name, entry["version"]) for name, entry in _entries()}
        archives = {
            path.relative_to(REGISTRY).as_posix()
            for path in (REGISTRY / "archives").rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        }
        self.assertEqual(archives, listed)


if __name__ == "__main__":
    unittest.main()
