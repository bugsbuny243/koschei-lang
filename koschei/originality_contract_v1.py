"""Fail-closed originality policy for Koschei's language and project surface.

This module does not claim mathematical uniqueness against every language ever
created. It enforces a narrower, auditable contract:

* inherited mainstream-looking syntax/layout is frozen as explicit migration debt;
* that debt can only shrink through a recorded retirement;
* new surface cannot silently reuse a curated set of common language/ecosystem
  spellings; and
* every new Koschei-native surface item needs design provenance tied to a Koschei
  invariant.

The compiler's current legacy grammar remains functional while it is migrated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


class OriginalityContractError(ValueError):
    """Raised when a language or project surface violates the originality gate."""


@dataclass(frozen=True, slots=True)
class SurfaceProvenance:
    invariant: str
    rationale: str
    collision_reviewed: bool


@dataclass(frozen=True, slots=True)
class OriginalityViolation:
    code: str
    subject: str
    detail: str


KOSCHEI_NATIVE_INVARIANTS_V1 = frozenset(
    {
        "authority-explicit",
        "authority-minimal",
        "deterministic-execution",
        "event-horizon-isolation",
        "protected-source-reality",
        "resource-linearity",
        "temporal-source-identity",
        "verifiable-effects",
    }
)

# Historical baseline. This set is migration debt, not approved design precedent.
LEGACY_KEYWORD_DEBT_V1 = frozenset(
    {
        "pure",
        "stateful",
        "fn",
        "let",
        "mut",
        "or",
        "return",
        "if",
        "else",
        "while",
        "for",
        "in",
        "break",
        "continue",
        "struct",
        "enum",
        "match",
        "import",
        "true",
        "false",
    }
)

# Migration ratchet. A retired item must never become active again.
RETIRED_LEGACY_KEYWORDS_V1 = frozenset()

# Historical punctuation/delimiter surface. Like keywords, these entries are debt.
LEGACY_SYMBOL_DEBT_V1 = frozenset(
    {
        "(",
        ")",
        "{",
        "}",
        "[",
        "]",
        ",",
        ":",
        ".",
        "=",
        "+",
        "-",
        "*",
        "/",
        "%",
        ";",
        "!",
        "<",
        ">",
        "->",
        "=>",
        "==",
        "!=",
        "<=",
        ">=",
        "&&",
        "||",
    }
)
RETIRED_LEGACY_SYMBOLS_V1 = frozenset()

# This is intentionally broad. It is a collision tripwire, not a list of all
# language spellings in existence.
BORROWED_KEYWORD_BLOCKLIST_V1 = frozenset(
    set(LEGACY_KEYWORD_DEBT_V1)
    | {
        "abstract",
        "alias",
        "as",
        "assert",
        "async",
        "await",
        "case",
        "catch",
        "chan",
        "class",
        "const",
        "contract",
        "crate",
        "def",
        "default",
        "defer",
        "delete",
        "do",
        "dyn",
        "event",
        "except",
        "export",
        "extends",
        "external",
        "finally",
        "from",
        "function",
        "go",
        "goto",
        "impl",
        "implements",
        "include",
        "interface",
        "internal",
        "lambda",
        "loop",
        "macro",
        "mapping",
        "memory",
        "mod",
        "modifier",
        "module",
        "namespace",
        "new",
        "package",
        "pass",
        "payable",
        "private",
        "protected",
        "pub",
        "public",
        "raise",
        "range",
        "ref",
        "require",
        "select",
        "self",
        "static",
        "storage",
        "super",
        "switch",
        "this",
        "throw",
        "trait",
        "try",
        "type",
        "typeof",
        "union",
        "unsafe",
        "use",
        "using",
        "var",
        "view",
        "virtual",
        "volatile",
        "where",
        "with",
        "yield",
    }
)

BORROWED_SYMBOL_BLOCKLIST_V1 = frozenset(
    set(LEGACY_SYMBOL_DEBT_V1)
    | {
        "::",
        ":=",
        "++",
        "--",
        "**",
        "//",
        "===",
        "!==",
        "??",
        "?.",
        "<-",
        "|>",
        "..",
        "...",
        "@",
        "#",
    }
)

# `ks new` currently emits these paths. They are frozen migration debt.
LEGACY_SCAFFOLD_PATH_DEBT_V1 = frozenset(
    {
        ".gitignore",
        "README.md",
        "koschei.toml",
        "src",
        "src/main.ks",
    }
)
RETIRED_LEGACY_SCAFFOLD_PATHS_V1 = frozenset()

# Current manifest vocabulary is also mainstream-shaped debt.
LEGACY_MANIFEST_VOCABULARY_DEBT_V1 = frozenset(
    {
        "package",
        "name",
        "version",
        "entry",
        "capabilities",
        "disk",
        "net",
        "env",
        "process",
    }
)
RETIRED_LEGACY_MANIFEST_VOCABULARY_V1 = frozenset()

BORROWED_LAYOUT_COMPONENTS_V1 = frozenset(
    {
        ".gitignore",
        "README.md",
        "app",
        "bin",
        "build",
        "cargo.toml",
        "cmd",
        "config",
        "dist",
        "docs",
        "examples",
        "go.mod",
        "include",
        "lib",
        "main",
        "main.ks",
        "manifest",
        "mod",
        "module",
        "modules",
        "node_modules",
        "package",
        "package.json",
        "packages",
        "pkg",
        "requirements.txt",
        "source",
        "src",
        "target",
        "test",
        "tests",
        "vendor",
    }
)

BORROWED_MANIFEST_WORDS_V1 = frozenset(
    set(LEGACY_MANIFEST_VOCABULARY_DEBT_V1)
    | {
        "author",
        "authors",
        "dependencies",
        "dependency",
        "description",
        "dev-dependencies",
        "features",
        "license",
        "module",
        "package",
        "repository",
        "scripts",
        "workspace",
    }
)

# Native surface is empty on purpose. New entries must be consciously registered
# here in the same change that introduces them.
NATIVE_KEYWORD_PROVENANCE_V1: Mapping[str, SurfaceProvenance] = {}
NATIVE_SYMBOL_PROVENANCE_V1: Mapping[str, SurfaceProvenance] = {}
NATIVE_SCAFFOLD_PROVENANCE_V1: Mapping[str, SurfaceProvenance] = {}
NATIVE_MANIFEST_PROVENANCE_V1: Mapping[str, SurfaceProvenance] = {}


def _clean_text(value: object, *, subject: str) -> str | None:
    if not isinstance(value, str):
        return None
    if not value or value != value.strip() or "\x00" in value:
        return None
    return value


def _validate_provenance(
    subject: str,
    provenance: SurfaceProvenance | None,
) -> list[OriginalityViolation]:
    if provenance is None:
        return [
            OriginalityViolation(
                "KO1002",
                subject,
                "new Koschei-native surface requires explicit design provenance",
            )
        ]
    if not isinstance(provenance, SurfaceProvenance):
        return [
            OriginalityViolation(
                "KO1003",
                subject,
                "provenance must use the canonical SurfaceProvenance record",
            )
        ]
    violations: list[OriginalityViolation] = []
    if provenance.invariant not in KOSCHEI_NATIVE_INVARIANTS_V1:
        violations.append(
            OriginalityViolation(
                "KO1003",
                subject,
                "provenance must bind the surface to a registered Koschei invariant",
            )
        )
    if (
        not isinstance(provenance.rationale, str)
        or len(provenance.rationale.strip()) < 24
        or provenance.rationale != provenance.rationale.strip()
        or "\x00" in provenance.rationale
    ):
        violations.append(
            OriginalityViolation(
                "KO1004",
                subject,
                "provenance rationale must be a canonical explanation of at least 24 characters",
            )
        )
    if provenance.collision_reviewed is not True:
        violations.append(
            OriginalityViolation(
                "KO1005",
                subject,
                "external syntax/layout collision review must be explicitly completed",
            )
        )
    return violations


def _audit_surface(
    current: Iterable[str],
    *,
    legacy: frozenset[str],
    retired: frozenset[str],
    blocked: frozenset[str],
    provenance: Mapping[str, SurfaceProvenance],
    subject_kind: str,
) -> tuple[OriginalityViolation, ...]:
    values: set[str] = set()
    violations: list[OriginalityViolation] = []
    for raw in current:
        value = _clean_text(raw, subject=subject_kind)
        if value is None:
            violations.append(
                OriginalityViolation(
                    "KO1000",
                    repr(raw),
                    f"{subject_kind} must be a non-empty canonical string without NUL",
                )
            )
            continue
        values.add(value)

    if not retired <= legacy:
        violations.append(
            OriginalityViolation(
                "KO1006",
                subject_kind,
                "retirement set contains items that were never part of legacy debt",
            )
        )

    active_legacy = legacy - retired
    missing_without_retirement = active_legacy - values
    if missing_without_retirement:
        violations.append(
            OriginalityViolation(
                "KO1007",
                subject_kind,
                "legacy debt disappeared without being recorded in the retirement ratchet: "
                + ", ".join(sorted(missing_without_retirement)),
            )
        )

    reintroduced = values & retired
    for value in sorted(reintroduced):
        violations.append(
            OriginalityViolation(
                "KO1008",
                value,
                "retired legacy surface cannot be reintroduced",
            )
        )

    native_values = values - legacy
    unregistered = native_values - set(provenance)
    for value in sorted(unregistered):
        if value in blocked:
            violations.append(
                OriginalityViolation(
                    "KO1001",
                    value,
                    f"new {subject_kind} collides with a blocked borrowed spelling",
                )
            )
        else:
            violations.extend(_validate_provenance(value, None))

    registered_but_absent = set(provenance) - native_values
    for value in sorted(registered_but_absent):
        violations.append(
            OriginalityViolation(
                "KO1009",
                value,
                "provenance registry contains surface that is not active",
            )
        )

    for value in sorted(native_values & set(provenance)):
        if value in blocked:
            violations.append(
                OriginalityViolation(
                    "KO1001",
                    value,
                    f"new {subject_kind} collides with a blocked borrowed spelling",
                )
            )
        violations.extend(_validate_provenance(value, provenance[value]))

    return tuple(violations)


def audit_keyword_surface(
    keywords: Iterable[str],
    *,
    provenance: Mapping[str, SurfaceProvenance] = NATIVE_KEYWORD_PROVENANCE_V1,
) -> tuple[OriginalityViolation, ...]:
    return _audit_surface(
        keywords,
        legacy=LEGACY_KEYWORD_DEBT_V1,
        retired=RETIRED_LEGACY_KEYWORDS_V1,
        blocked=BORROWED_KEYWORD_BLOCKLIST_V1,
        provenance=provenance,
        subject_kind="keyword",
    )


def audit_symbol_surface(
    symbols: Iterable[str],
    *,
    provenance: Mapping[str, SurfaceProvenance] = NATIVE_SYMBOL_PROVENANCE_V1,
) -> tuple[OriginalityViolation, ...]:
    return _audit_surface(
        symbols,
        legacy=LEGACY_SYMBOL_DEBT_V1,
        retired=RETIRED_LEGACY_SYMBOLS_V1,
        blocked=BORROWED_SYMBOL_BLOCKLIST_V1,
        provenance=provenance,
        subject_kind="symbol",
    )


def audit_scaffold_surface(
    paths: Iterable[str],
    *,
    provenance: Mapping[str, SurfaceProvenance] = NATIVE_SCAFFOLD_PROVENANCE_V1,
) -> tuple[OriginalityViolation, ...]:
    normalized: list[str] = []
    violations: list[OriginalityViolation] = []
    for raw in paths:
        value = _clean_text(raw, subject="scaffold path")
        if value is None:
            violations.append(
                OriginalityViolation(
                    "KO1000",
                    repr(raw),
                    "scaffold path must be a non-empty canonical string without NUL",
                )
            )
            continue
        if value.startswith("/") or "\\" in value or "//" in value:
            violations.append(
                OriginalityViolation(
                    "KO1010",
                    value,
                    "canonical scaffold paths must be relative POSIX paths",
                )
            )
            continue
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            violations.append(
                OriginalityViolation(
                    "KO1010",
                    value,
                    "canonical scaffold path contains an unsafe or ambiguous component",
                )
            )
            continue
        normalized.append(value)

    surface = _audit_surface(
        normalized,
        legacy=LEGACY_SCAFFOLD_PATH_DEBT_V1,
        retired=RETIRED_LEGACY_SCAFFOLD_PATHS_V1,
        blocked=frozenset(),
        provenance=provenance,
        subject_kind="scaffold path",
    )
    violations.extend(surface)

    legacy_paths = LEGACY_SCAFFOLD_PATH_DEBT_V1
    for path in sorted(set(normalized) - legacy_paths):
        for component in path.split("/"):
            lowered = component.casefold()
            stem = lowered.rsplit(".", 1)[0] if "." in lowered else lowered
            if lowered in BORROWED_LAYOUT_COMPONENTS_V1 or stem in BORROWED_LAYOUT_COMPONENTS_V1:
                violations.append(
                    OriginalityViolation(
                        "KO1011",
                        path,
                        f"new canonical layout reuses conventional component {component!r}",
                    )
                )
                break
    return tuple(violations)


def audit_manifest_vocabulary(
    words: Iterable[str],
    *,
    provenance: Mapping[str, SurfaceProvenance] = NATIVE_MANIFEST_PROVENANCE_V1,
) -> tuple[OriginalityViolation, ...]:
    return _audit_surface(
        words,
        legacy=LEGACY_MANIFEST_VOCABULARY_DEBT_V1,
        retired=RETIRED_LEGACY_MANIFEST_VOCABULARY_V1,
        blocked=BORROWED_MANIFEST_WORDS_V1,
        provenance=provenance,
        subject_kind="manifest word",
    )


def enforce_no_violations(
    violations: Iterable[OriginalityViolation],
) -> None:
    collected = tuple(violations)
    if not collected:
        return
    rendered = "; ".join(
        f"{item.code} {item.subject}: {item.detail}" for item in collected
    )
    raise OriginalityContractError(rendered)


def active_legacy_debt_v1() -> dict[str, tuple[str, ...]]:
    """Return the exact debt that still blocks Koschei-native-surface maturity."""

    return {
        "keywords": tuple(sorted(LEGACY_KEYWORD_DEBT_V1 - RETIRED_LEGACY_KEYWORDS_V1)),
        "symbols": tuple(sorted(LEGACY_SYMBOL_DEBT_V1 - RETIRED_LEGACY_SYMBOLS_V1)),
        "scaffold_paths": tuple(
            sorted(
                LEGACY_SCAFFOLD_PATH_DEBT_V1
                - RETIRED_LEGACY_SCAFFOLD_PATHS_V1
            )
        ),
        "manifest_vocabulary": tuple(
            sorted(
                LEGACY_MANIFEST_VOCABULARY_DEBT_V1
                - RETIRED_LEGACY_MANIFEST_VOCABULARY_V1
            )
        ),
    }
