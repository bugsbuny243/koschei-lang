from __future__ import annotations

from koschei.ast_nodes import (
    EnumDeclaration,
    EnumVariant,
    Identifier,
    Literal,
    MatchArm,
    MatchExpression,
    Program,
    SourceLocation,
    TypeRef,
)
from koschei.typed_hir import TypedHIRChecker
from koschei.type_system import INT, NamedType, generic


def _loc() -> SourceLocation:
    return SourceLocation(1, 1)


def test_option_match_records_canonical_owner_payload_and_exhaustiveness() -> None:
    location = _loc()
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})
    expression = MatchExpression(
        Identifier("choice", location),
        (
            MatchArm(
                "Some",
                "payload",
                Identifier("payload", location),
                location,
            ),
            MatchArm("None", None, Literal(0, location), location),
        ),
        location,
    )

    checker.infer(expression)

    assert len(checker.match_resolutions) == 1
    fact = checker.match_resolutions[0]
    assert fact.expression is expression
    assert fact.value_type == generic("Option", INT)
    assert fact.exhaustive is True
    assert tuple(arm.canonical_variant for arm in fact.arms) == (
        "Option::Some",
        "Option::None",
    )
    assert fact.arms[0].payload_type == INT
    assert fact.arms[0].binding_type == INT
    assert fact.arms[1].payload_type is None
    assert fact.arms[1].binding_type is None


def test_unresolved_visible_variant_does_not_create_authoritative_match_fact() -> None:
    location = _loc()
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})
    expression = MatchExpression(
        Identifier("choice", location),
        (MatchArm("Some", "payload", Literal(1, location), location),
         MatchArm("Other", None, Literal(0, location), location)),
        location,
    )

    checker.infer(expression)

    assert checker.match_resolutions == []


def test_same_visible_variant_is_resolved_by_scrutinee_owner_not_global_name() -> None:
    location = _loc()
    payload = TypeRef(("Int",), location)
    alpha = EnumDeclaration(
        "Alpha",
        (EnumVariant("Some", payload, location), EnumVariant("None", None, location)),
        location,
    )
    beta = EnumDeclaration(
        "Beta",
        (EnumVariant("Some", payload, location), EnumVariant("None", None, location)),
        location,
    )
    checker = TypedHIRChecker(Program((), enums=(alpha, beta)))

    alpha_resolution = checker.resolve_match_variant(NamedType("Alpha"), "Some")
    beta_resolution = checker.resolve_match_variant(NamedType("Beta"), "Some")

    assert alpha_resolution is not None
    assert beta_resolution is not None
    assert alpha_resolution[0] == "Alpha"
    assert beta_resolution[0] == "Beta"
    assert alpha_resolution[1] == INT
    assert beta_resolution[1] == INT


def test_partial_match_is_recorded_but_not_marked_exhaustive() -> None:
    location = _loc()
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})
    expression = MatchExpression(
        Identifier("choice", location),
        (MatchArm("Some", "payload", Literal(1, location), location),),
        location,
    )

    checker.infer(expression)

    assert len(checker.match_resolutions) == 1
    assert checker.match_resolutions[0].exhaustive is False
    assert checker.match_resolutions[0].arms[0].canonical_variant == "Option::Some"
