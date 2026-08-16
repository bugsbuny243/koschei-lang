from __future__ import annotations

import itertools
import re
import string
import tempfile
import tomllib
import unittest
from pathlib import Path

from koschei.lexer import Lexer, LexerError, TokenType, tokenize
from koschei.originality_contract_v1 import (
    BORROWED_LAYOUT_COMPONENTS_V1,
    LEGACY_KEYWORD_DEBT_V1,
    LEGACY_MANIFEST_VOCABULARY_DEBT_V1,
    LEGACY_SCAFFOLD_PATH_DEBT_V1,
    LEGACY_SYMBOL_DEBT_V1,
    SurfaceProvenance,
    active_legacy_debt_v1,
    audit_keyword_surface,
    audit_manifest_vocabulary,
    audit_scaffold_surface,
    audit_symbol_surface,
)
from koschei.project import create_project


REPO_ROOT = Path(__file__).resolve().parents[1]


def _codes(violations) -> set[str]:
    return {item.code for item in violations}


def _discover_atomic_ascii_symbols() -> frozenset[str]:
    # Discover behavior, not implementation constants. A new one-, two-, or
    # three-character punctuation token becomes visible to this gate.
    ignored = {
        TokenType.TYPE,
        TokenType.IDENTIFIER,
        TokenType.STRING,
        TokenType.STRING_INTERP,
        TokenType.NUMBER,
        TokenType.COMMENT,
        TokenType.EOF,
    }
    found: set[str] = set()
    alphabet = string.punctuation
    for width in (1, 2, 3):
        for chars in itertools.product(alphabet, repeat=width):
            candidate = "".join(chars)
            try:
                tokens = tokenize(candidate)
            except LexerError:
                continue
            payload = [token for token in tokens if token.type is not TokenType.EOF]
            if (
                len(payload) == 1
                and payload[0].type not in ignored
                and payload[0].value == candidate
            ):
                found.add(candidate)
    return frozenset(found)


def _native_keyword_surface() -> frozenset[str]:
    base = (REPO_ROOT / "native" / "lexer" / "lexer.go").read_text(
        encoding="utf-8"
    )
    extensions = (
        REPO_ROOT / "native" / "lexer" / "high_assurance_keywords.go"
    ).read_text(encoding="utf-8")
    base_terms = set(
        re.findall(r'"([a-z][a-z0-9_]*)"\s*:\s*[A-Z][A-Z0-9_]*', base)
    )
    extension_terms = set(
        re.findall(r'keywords\["([a-z][a-z0-9_]*)"\]\s*=', extensions)
    )
    return frozenset(base_terms | extension_terms)


def _manifest_vocabulary(path: Path) -> frozenset[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    words: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                words.add(key)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return frozenset(words)


class LiveOriginalityRatchetTests(unittest.TestCase):
    def test_python_keyword_surface_is_exactly_frozen_legacy_debt(self) -> None:
        current = frozenset(Lexer.KEYWORDS)
        self.assertEqual(current, LEGACY_KEYWORD_DEBT_V1)
        self.assertEqual(audit_keyword_surface(current), ())

    def test_native_keyword_surface_matches_python_oracle_and_debt(self) -> None:
        native = _native_keyword_surface()
        self.assertEqual(native, frozenset(Lexer.KEYWORDS))
        self.assertEqual(native, LEGACY_KEYWORD_DEBT_V1)

    def test_atomic_symbol_surface_is_exactly_frozen_legacy_debt(self) -> None:
        current = _discover_atomic_ascii_symbols()
        self.assertEqual(current, LEGACY_SYMBOL_DEBT_V1)
        self.assertEqual(audit_symbol_surface(current), ())

    def test_current_scaffold_is_frozen_as_debt_not_native_design(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = create_project("originality_probe", Path(directory) / "probe")
            paths = frozenset(
                path.relative_to(project.root).as_posix()
                for path in project.root.rglob("*")
            )
            self.assertEqual(paths, LEGACY_SCAFFOLD_PATH_DEBT_V1)
            self.assertEqual(audit_scaffold_surface(paths), ())

            vocabulary = _manifest_vocabulary(project.manifest)
            self.assertEqual(
                vocabulary,
                LEGACY_MANIFEST_VOCABULARY_DEBT_V1,
            )
            self.assertEqual(audit_manifest_vocabulary(vocabulary), ())

    def test_debt_is_reported_as_active_maturity_blocker(self) -> None:
        debt = active_legacy_debt_v1()
        self.assertTrue(debt["keywords"])
        self.assertTrue(debt["symbols"])
        self.assertTrue(debt["scaffold_paths"])
        self.assertTrue(debt["manifest_vocabulary"])


class AntiCopyGateTests(unittest.TestCase):
    def test_new_borrowed_keyword_is_rejected(self) -> None:
        violations = audit_keyword_surface(
            set(LEGACY_KEYWORD_DEBT_V1) | {"class"}
        )
        self.assertIn("KO1001", _codes(violations))

    def test_new_unregistered_native_keyword_is_rejected(self) -> None:
        violations = audit_keyword_surface(
            set(LEGACY_KEYWORD_DEBT_V1) | {"veil"}
        )
        self.assertIn("KO1002", _codes(violations))

    def test_new_native_keyword_requires_koschei_invariant_and_review(self) -> None:
        provenance = {
            "veil": SurfaceProvenance(
                invariant="protected-source-reality",
                rationale=(
                    "Names a Koschei source-reality boundary rather than "
                    "mirroring another language construct."
                ),
                collision_reviewed=True,
            )
        }
        violations = audit_keyword_surface(
            set(LEGACY_KEYWORD_DEBT_V1) | {"veil"},
            provenance=provenance,
        )
        self.assertEqual(violations, ())

    def test_cosmetic_keyword_rename_cannot_skip_provenance(self) -> None:
        provenance = {
            "veil": SurfaceProvenance(
                invariant="syntax-is-pretty",
                rationale="renamed from a familiar language keyword",
                collision_reviewed=False,
            )
        }
        violations = audit_keyword_surface(
            set(LEGACY_KEYWORD_DEBT_V1) | {"veil"},
            provenance=provenance,
        )
        self.assertTrue({"KO1003", "KO1005"} <= _codes(violations))

    def test_legacy_keyword_removal_must_advance_retirement_ratchet(self) -> None:
        current = set(LEGACY_KEYWORD_DEBT_V1)
        current.remove("fn")
        self.assertIn("KO1007", _codes(audit_keyword_surface(current)))

    def test_new_conventional_layout_is_rejected(self) -> None:
        provenance = {
            "src/veil.ks": SurfaceProvenance(
                invariant="protected-source-reality",
                rationale=(
                    "Registers an experimental source path only for collision "
                    "testing of the originality gate."
                ),
                collision_reviewed=True,
            )
        }
        violations = audit_scaffold_surface(
            set(LEGACY_SCAFFOLD_PATH_DEBT_V1) | {"src/veil.ks"},
            provenance=provenance,
        )
        self.assertIn("KO1011", _codes(violations))

    def test_new_unique_layout_still_requires_provenance(self) -> None:
        violations = audit_scaffold_surface(
            set(LEGACY_SCAFFOLD_PATH_DEBT_V1) | {"veil.anchor"}
        )
        self.assertIn("KO1002", _codes(violations))

    def test_new_borrowed_manifest_word_is_rejected(self) -> None:
        violations = audit_manifest_vocabulary(
            set(LEGACY_MANIFEST_VOCABULARY_DEBT_V1) | {"dependencies"}
        )
        self.assertIn("KO1001", _codes(violations))

    def test_layout_blocklist_keeps_known_ecosystem_names_out(self) -> None:
        for name in ("src", "lib", "bin", "build", "dist", "target", "main"):
            self.assertIn(name, BORROWED_LAYOUT_COMPONENTS_V1)


if __name__ == "__main__":
    unittest.main()
