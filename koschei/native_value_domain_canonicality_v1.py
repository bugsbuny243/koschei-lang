"""Canonicality hardening for Koschei native value domains v1.

Two properties are enforced below the surface grammar:

* bidirectional source controls are rejected so displayed source cannot reorder
  grammar/payload text for a reviewer; and
* derived ``glyphs`` values are normalized to NFC after every merge, so two
  individually canonical operands cannot create a non-canonical value at their
  concatenation boundary.

This module changes no source vocabulary and introduces no implicit cross-domain
coercion.  It installs into the native-value frontend before Object Space
routing is enabled.
"""

from __future__ import annotations

import unicodedata

from . import native_value_domains_v1 as _domains


_BIDI_CONTROLS = frozenset(
    {
        "\u061c",  # ARABIC LETTER MARK
        "\u200e",  # LEFT-TO-RIGHT MARK
        "\u200f",  # RIGHT-TO-LEFT MARK
        "\u202a",  # LEFT-TO-RIGHT EMBEDDING
        "\u202b",  # RIGHT-TO-LEFT EMBEDDING
        "\u202c",  # POP DIRECTIONAL FORMATTING
        "\u202d",  # LEFT-TO-RIGHT OVERRIDE
        "\u202e",  # RIGHT-TO-LEFT OVERRIDE
        "\u2066",  # LEFT-TO-RIGHT ISOLATE
        "\u2067",  # RIGHT-TO-LEFT ISOLATE
        "\u2068",  # FIRST STRONG ISOLATE
        "\u2069",  # POP DIRECTIONAL ISOLATE
    }
)

_INSTALLED = False
_ORIGINAL_CANONICAL_LINES = _domains._canonical_lines


def _canonical_lines_hardened(source: object) -> tuple[str, ...]:
    if isinstance(source, str):
        for offset, char in enumerate(source):
            if char in _BIDI_CONTROLS:
                line = source.count("\n", 0, offset) + 1
                line_start = source.rfind("\n", 0, offset) + 1
                column = offset - line_start + 1
                _domains._fail(
                    "KV1007",
                    "bidirectional control characters are forbidden in native value source",
                    line,
                    column,
                )
    return _ORIGINAL_CANONICAL_LINES(source)


def _evaluate_canonical_value_graph(
    graph: _domains.NativeValueGraph,
) -> dict[str, _domains.NativeValue]:
    by_name = graph.by_name()
    values: dict[str, _domains.NativeValue] = {}

    def atom_value(atom: _domains.ValueAtom) -> _domains.NativeValue:
        if atom.literal is not None:
            return atom.literal
        assert atom.witness is not None
        return values[atom.witness]

    for name in _domains.dependency_order_value_graph(graph):
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            value = atom_value(term.atoms[0])
        else:
            left = atom_value(term.atoms[0])
            right = atom_value(term.atoms[1])
            operation = term.operation
            if operation in _domains._NUMERIC_OPS:
                if left.domain != _domains.WHOLE or right.domain != _domains.WHOLE:
                    _domains._fail(
                        "KV1401",
                        f"{operation} requires whole/whole and forbids coercion",
                        witness.location.line,
                        1,
                    )
                a = int(left.value)
                b = int(right.value)
                if operation == "sum":
                    result = a + b
                elif operation == "difference":
                    result = a - b
                else:
                    result = a * b
                if not _domains.INT_MIN <= result <= _domains.INT_MAX:
                    _domains._fail(
                        "KV1402",
                        f"{operation} exceeds signed Int64 reality",
                        witness.location.line,
                        1,
                    )
                value = _domains.NativeValue(_domains.WHOLE, result)
            elif operation == "same":
                if left.domain != right.domain:
                    _domains._fail(
                        "KV1403",
                        "same requires identical value domains and forbids cross-domain equality coercion",
                        witness.location.line,
                        1,
                    )
                value = _domains.NativeValue(_domains.TRUTH, left.value == right.value)
            elif operation == "merge":
                if left.domain != _domains.GLYPHS or right.domain != _domains.GLYPHS:
                    _domains._fail(
                        "KV1404",
                        "merge requires glyphs/glyphs and forbids textual coercion",
                        witness.location.line,
                        1,
                    )
                merged = unicodedata.normalize(
                    "NFC", str(left.value) + str(right.value)
                )
                if len(merged.encode("utf-8")) > _domains.MAX_GLYPHS_RESULT_BYTES:
                    _domains._fail(
                        "KV1405",
                        "merged glyphs exceeds result byte budget",
                        witness.location.line,
                        1,
                    )
                value = _domains.NativeValue(_domains.GLYPHS, merged)
            else:
                _domains._fail(
                    "KV1005",
                    f"unknown value operation {operation!r}",
                    witness.location.line,
                    1,
                )
        values[name] = value
    return values


def install_native_value_domain_canonicality_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _domains._canonical_lines = _canonical_lines_hardened
    _domains.evaluate_native_value_graph = _evaluate_canonical_value_graph
    _INSTALLED = True
