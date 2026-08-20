"""Canonical capability view for the legacy semantic checker.

The legacy semantic checker remains the compatibility implementation for a
subset of language rules, but capability shape is no longer allowed to be
owned by semantic.py.  This module installs mutable compatibility views derived
from the canonical capability contract before delegating to semantic.check().

The mutation is intentional and process-local: semantic.py historically reads
module globals such as ROOT_METHODS while walking expressions.  Replacing
those globals here removes the duplicate authority from the compiler path
without rewriting the entire legacy checker in one risky change.
"""
from __future__ import annotations

from . import semantic as _legacy
from .capability_effect_contract_v1 import (
    CAPABILITY_TYPES,
    GUARDED_METHODS,
    NET_ORIGIN_SCHEMES,
    NARROWING_METHODS,
    ROOT_CAPABILITY_TYPES,
    legacy_narrowed_operations,
    legacy_root_narrowing,
    legacy_system_capability_members,
)


def _install_canonical_capability_view() -> None:
    """Replace legacy capability globals with canonical-derived views.

    Fresh dict/set objects preserve semantic.py's historical mutable types while
    ensuring the data itself originates from the canonical contract.
    """

    _legacy.CAPABILITY_MEMBERS = legacy_system_capability_members()
    _legacy.ROOT_METHODS = legacy_root_narrowing()
    _legacy.NARROWED_METHODS = legacy_narrowed_operations()
    _legacy.NARROWING_METHODS = set(NARROWING_METHODS)
    _legacy.GUARDED_METHODS = set(GUARDED_METHODS)
    _legacy.CAPABILITY_TYPES = set(CAPABILITY_TYPES)
    _legacy.ROOT_CAPABILITY_TYPES = set(ROOT_CAPABILITY_TYPES)
    _legacy.NET_ORIGIN_SCHEMES = NET_ORIGIN_SCHEMES


_install_canonical_capability_view()

ImportedModule = _legacy.ImportedModule
SemanticError = _legacy.SemanticError
SemanticReport = _legacy.SemanticReport
SemanticChecker = _legacy.SemanticChecker


def check(program, imports=None):
    """Run the legacy checker under the canonical capability contract."""

    # Re-install before each check so external compatibility code cannot mutate
    # the legacy views and thereby affect a later compiler invocation.
    _install_canonical_capability_view()
    return _legacy.check(program, imports)
