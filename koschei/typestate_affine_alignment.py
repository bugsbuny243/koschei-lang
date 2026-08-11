"""Bind typestate resources into the existing affine ownership checker."""

from __future__ import annotations

from . import affine_resources_v1 as _affine
from .typestate_resources_v1 import is_typestate_affine

_INSTALLED = False
_ORIGINAL_IS_AFFINE = None


def install_typestate_affine_alignment() -> None:
    global _INSTALLED, _ORIGINAL_IS_AFFINE
    if _INSTALLED:
        return

    _ORIGINAL_IS_AFFINE = _affine.AffineResourceChecker._is_affine

    def _is_affine(checker, type_node):
        return _ORIGINAL_IS_AFFINE(checker, type_node) or is_typestate_affine(
            type_node, checker.contracts
        )

    _affine.AffineResourceChecker._is_affine = _is_affine
    _INSTALLED = True
