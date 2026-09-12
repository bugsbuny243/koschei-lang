from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import MatchExpression, Program, SourceLocation
from .type_contracts import declaration_type, type_parameters_of
from .type_system import GenericType, NamedType, TypeNode, UNKNOWN, substitute_type
from .typed_hir import TypedHIRReport


@dataclass(frozen=True, slots=True)
class MatchArmSemanticV1:
    """Compiler-owned semantic identity for one checked match arm."""

    variant_identity: str | None
    variant_name: str
    binding: str | None
    payload_type: TypeNode | None
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MatchSemanticV1:
    """Canonical checked facts consumed by future explicit MIR match lowering."""

    value_type: TypeNode
    enum_identity: str | None
    arms: tuple[MatchArmSemanticV1, ...]
    exhaustive: bool


def _recorded_type(report: TypedHIRReport, expression) -> TypeNode:
    for item in reversed(report.expressions):
        if item.expression is expression:
            return item.type
    return UNKNOWN


def _enum_declaration(program: Program, imports, name: str):
    for declaration in program.enums:
        if declaration.name == name:
            return declaration
    for module in (imports or {}).values():
        declaration = getattr(module, "enums", {}).get(name)
        if declaration is not None:
            return declaration
    return None


def _enum_shape(program: Program, imports, value_type: TypeNode):
    if isinstance(value_type, GenericType):
        if value_type.name == "Option":
            return "Option", ("Some", "None"), None, {}
        if value_type.name == "Result":
            return "Result", ("Ok", "Err"), None, {}
        declaration = _enum_declaration(program, imports, value_type.name)
        if declaration is not None:
            mapping = dict(zip(type_parameters_of(declaration), value_type.arguments))
            return value_type.name, tuple(item.name for item in declaration.variants), declaration, mapping
    if isinstance(value_type, NamedType):
        declaration = _enum_declaration(program, imports, value_type.name)
        if declaration is not None:
            return value_type.name, tuple(item.name for item in declaration.variants), declaration, {}
    return None, (), None, {}


def _payload_type_from_report(report: TypedHIRReport, arm) -> TypeNode | None:
    if arm.binding is None:
        return None
    for item in reversed(report.bindings):
        if (
            item.role == "match-payload"
            and item.name == arm.binding
            and item.location == arm.location
        ):
            return item.type
    return UNKNOWN


def resolve_match_semantics_v1(
    program: Program,
    report: TypedHIRReport,
    expression: MatchExpression,
    imports=None,
) -> MatchSemanticV1:
    """Resolve match identity only from already-checked compiler products.

    This helper deliberately does not inspect runtime values. It exposes the
    minimum semantic authority required before MatchExpression may leave
    MirAstFallback: enum identity, ordered arm identities, payload types and the
    compiler-side exhaustiveness fact.
    """

    value_type = _recorded_type(report, expression.value)
    enum_identity, allowed_variants, declaration, mapping = _enum_shape(
        program, imports, value_type
    )
    allowed = set(allowed_variants)
    arms: list[MatchArmSemanticV1] = []
    seen: set[str] = set()

    for arm in expression.arms:
        identity = None
        if enum_identity is not None and arm.variant in allowed:
            identity = f"{enum_identity}::{arm.variant}"
        payload_type = _payload_type_from_report(report, arm)
        if payload_type is None and declaration is not None:
            variant = next(
                (item for item in declaration.variants if item.name == arm.variant),
                None,
            )
            if variant is not None and variant.payload_type is not None:
                payload_type = substitute_type(
                    declaration_type(declaration, variant.payload_type), mapping
                )
        arms.append(
            MatchArmSemanticV1(
                identity,
                arm.variant,
                arm.binding,
                payload_type,
                arm.location,
            )
        )
        if identity is not None:
            seen.add(arm.variant)

    exhaustive = bool(allowed_variants) and seen == allowed and all(
        arm.variant_identity is not None for arm in arms
    )
    return MatchSemanticV1(value_type, enum_identity, tuple(arms), exhaustive)


__all__ = ["MatchArmSemanticV1", "MatchSemanticV1", "resolve_match_semantics_v1"]
