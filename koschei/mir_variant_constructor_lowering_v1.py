"""Canonical lowering for enum/Option/Result constructor calls.

Koschei grammar reserves lowercase identifiers for function declarations and
uppercase identifiers for type/variant constructors.  This lowerer therefore
never asks a backend to resolve a visible variant name to an owner.  The owner
comes only from the already-checked Typed-HIR result type of the call; the
surface variant token is preserved verbatim and sealed as ``Owner::Variant``.

This is a representation projection, not a new semantic resolver.  If the
checked type is unavailable or the constructor shape is ambiguous, lowering
returns ``None`` so callers can preserve the existing fail-closed boundary.
"""
from __future__ import annotations

from .ast_nodes import CallExpression, Identifier
from .mir_extension_instructions_v4 import MirVariantConstruct
from .type_system import GenericType, NamedType, UnknownType


_BUILTIN_VARIANT_ARITY = {
    "Some": 1,
    "None": 0,
    "Ok": 1,
    "Err": 1,
}


def _owner_from_checked_type(type_node) -> str | None:
    if isinstance(type_node, GenericType):
        return type_node.name
    if isinstance(type_node, NamedType):
        return type_node.name
    if isinstance(type_node, UnknownType):
        return None
    return None


def lower_variant_constructor_v1(lowerer, expression: CallExpression) -> int | None:
    """Emit ``MirVariantConstruct`` for one checked constructor call.

    Returns ``None`` when the expression is not syntactically a variant
    constructor or when Typed-HIR did not provide a concrete owner type.
    """

    callee = expression.callee
    if not isinstance(callee, Identifier):
        return None
    variant = callee.name
    if not variant or not variant[0].isupper() or variant == "Error":
        return None

    result_type = lowerer._type_of(expression)
    owner = _owner_from_checked_type(result_type)
    if owner is None or owner.startswith("Module:") or "::" in owner:
        return None

    # Builtin sum constructors have fixed public arity. User enum arity was
    # already checked by Typed-HIR; executable MIR supports only zero/one
    # payload variants, matching the language enum declaration grammar.
    expected = _BUILTIN_VARIANT_ARITY.get(variant)
    if expected is not None and len(expression.arguments) != expected:
        raise ValueError(
            f"checked builtin variant constructor arity drifted for {variant}: "
            f"expected {expected}, got {len(expression.arguments)}"
        )
    if len(expression.arguments) > 1:
        raise ValueError("variant constructors support at most one payload")

    source = None
    if expression.arguments:
        source = lowerer._lower_expression(expression.arguments[0])

    target = lowerer._new_value()
    lowerer._emit(
        MirVariantConstruct(
            target=target,
            variant=f"{owner}::{variant}",
            source=source,
            type=result_type,
            location=expression.location,
        )
    )
    return target


__all__ = ["lower_variant_constructor_v1"]
