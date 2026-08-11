"""Compatibility gate for BoundedQueue generic signatures.

Typed HIR retains `BoundedQueue<T>` structurally, but the legacy compatibility
checker flattens old TypeRef data and may retain only `BoundedQueue` for a function
parameter. This bridge lets the legacy pass consume calls whose exact generic
contract was already proven by Typed HIR while still rejecting genuinely raw
`BoundedQueue` source annotations structurally.
"""

from __future__ import annotations

from . import semantic as _semantic
from . import type_contracts as _contracts
from .ast_nodes import CallExpression, Identifier
from .type_system import NamedType

_INSTALLED = False
_ORIGINAL_LEGACY_VALIDATE = None
_ORIGINAL_STRUCTURAL_VALIDATE = None
_ORIGINAL_LEGACY_EXPRESSION = None
_QUEUE_METHODS = {
    "queue_try_send",
    "queue_try_recv",
    "queue_len",
    "queue_capacity",
}


def _legacy_validate(self, type_name, location):
    # `TypeRef.names` exposes the container token separately even for a real
    # `BoundedQueue<Int>` annotation. Typed HIR validates the actual structure
    # before the legacy semantic pass is entered by modules.check_graph().
    if type_name == "BoundedQueue":
        return
    return _ORIGINAL_LEGACY_VALIDATE(self, type_name, location)


def _structural_validate(self, type_node, location, subject):
    # Unlike v0.9 raw List/Map compatibility, BoundedQueue has no raw ABI. The
    # structural checker therefore rejects a source annotation that truly omits T.
    if isinstance(type_node, NamedType) and type_node.name == "BoundedQueue":
        raise _semantic.SemanticError(
            "KS1301",
            f"{subject}: BoundedQueue tipi BoundedQueue<T> biçiminde kullanılmalıdır.",
            location,
        )
    return _ORIGINAL_STRUCTURAL_VALIDATE(self, type_node, location, subject)


def _legacy_expression(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _QUEUE_METHODS
        and expression.arguments
    ):
        name = expression.callee.name
        expected = 2 if name == "queue_try_send" else 1
        if len(expression.arguments) != expected:
            raise _semantic.SemanticError(
                "KS1301",
                f"{name}() {expected} argüman bekler, {len(expression.arguments)} verildi.",
                expression.location,
            )
        queue_type = self._check_expression(expression.arguments[0])
        if queue_type == "BoundedQueue":
            # The legacy Symbol table lost T at the function boundary. Do not
            # invent it here. Typed HIR has already checked the exact queue/item
            # contract; this compatibility pass only needs a conservative legacy
            # result so it does not reject a structurally proven program.
            if name == "queue_try_send":
                self._check_expression(expression.arguments[1])
                return "Bool"
            if name == "queue_try_recv":
                return "_ or Error"
            return "Int"
    return _ORIGINAL_LEGACY_EXPRESSION(self, expression)


def install_bounded_queue_contract_gate() -> None:
    global _INSTALLED
    global _ORIGINAL_LEGACY_VALIDATE, _ORIGINAL_STRUCTURAL_VALIDATE
    global _ORIGINAL_LEGACY_EXPRESSION
    if _INSTALLED:
        return
    _ORIGINAL_LEGACY_VALIDATE = _semantic.SemanticChecker._validate_generic_type
    _semantic.SemanticChecker._validate_generic_type = _legacy_validate
    _ORIGINAL_STRUCTURAL_VALIDATE = _contracts.TypeContractValidator.validate_type
    _contracts.TypeContractValidator.validate_type = _structural_validate
    _ORIGINAL_LEGACY_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _legacy_expression
    _INSTALLED = True
