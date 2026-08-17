"""Strict lexical identity for exact-object persistence policy v1.

Exact authority should not silently reinterpret a source literal. Whitespace
trimming or lexical `..`/duplicate-separator normalization can make the runtime
object differ from the path a reviewer sees in source. V1 therefore accepts only
an already-canonical absolute path and rejects aliases instead of rewriting them.
"""

from __future__ import annotations

import os

from . import persistence_authority_v1 as _authority

_INSTALLED = False


def _canonical_exact_path(raw: str) -> str | None:
    if "\x00" in raw or raw != raw.strip():
        return None
    if not raw or not os.path.isabs(raw):
        return None
    canonical = os.path.normpath(raw)
    if canonical != raw or canonical == os.path.sep:
        return None
    name = os.path.basename(canonical)
    if not name or name in {".", ".."}:
        return None
    return canonical


def install_persistence_policy_canonical_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _authority._canonical_exact_path = _canonical_exact_path
    _INSTALLED = True
