"""Semantic registry integrity for persistence v1."""

from __future__ import annotations

from . import semantic as _semantic

_INSTALLED = False


def install_persistence_semantic_alignment_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    methods = {"load", "commit"}
    _semantic.NARROWED_METHODS["PersistCaps"] = methods
    _semantic.GUARDED_METHODS.update(methods)
    _INSTALLED = True
