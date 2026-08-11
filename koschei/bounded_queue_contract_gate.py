"""Compatibility gate for BoundedQueue generic signatures.

The legacy semantic checker flattens a generic TypeRef into individual names, so
`BoundedQueue<Int>` is observed once as the bare token `BoundedQueue` and once as
`Int`. Typed HIR retains the actual GenericType structure. This bridge tolerates
only that legacy token while making the structural checker reject a genuinely raw
`BoundedQueue` source annotation.
"""

from __future__ import annotations

from . import semantic as _semantic
from . import type_contracts as _contracts
from .type_system import NamedType

_INSTALLED = False
_ORIGINAL_LEGACY_VALIDATE = None
_ORIGINAL_STRUCTURAL_VALIDATE = None


def _legacy_validate(self, type_name, location):
    if type_name == "BoundedQueue":
        return
    return _ORIGINAL_LEGACY_VALIDATE(self, type_name, location)


def _structural_validate(self, type_node, location, subject):
    if isinstance(type_node, NamedType) and type_node.name == "BoundedQueue":
        raise _semantic.SemanticError(
            "KS1301",
            f"{subject}: BoundedQueue tipi BoundedQueue<T> biçiminde kullanılmalıdır.",
            location,
        )
    return _ORIGINAL_STRUCTURAL_VALIDATE(self, type_node, location, subject)


def install_bounded_queue_contract_gate() -> None:
    global _INSTALLED, _ORIGINAL_LEGACY_VALIDATE, _ORIGINAL_STRUCTURAL_VALIDATE
    if _INSTALLED:
        return
    _ORIGINAL_LEGACY_VALIDATE = _semantic.SemanticChecker._validate_generic_type
    _semantic.SemanticChecker._validate_generic_type = _legacy_validate
    _ORIGINAL_STRUCTURAL_VALIDATE = _contracts.TypeContractValidator.validate_type
    _contracts.TypeContractValidator.validate_type = _structural_validate
    _INSTALLED = True
