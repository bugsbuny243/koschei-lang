from koschei.ast_nodes import (
    Block,
    EnumDeclaration,
    EnumVariant,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    Literal,
    MatchArm,
    MatchExpression,
    Parameter,
    Program,
    SourceLocation,
    TypeRef,
)
from koschei.match_semantics_v1 import resolve_match_semantics_v1
from koschei.typed_hir import lower_typed_hir
from koschei.type_system import INT, UNKNOWN


def _loc(column: int = 1) -> SourceLocation:
    return SourceLocation(1, column)


def test_custom_enum_match_exposes_canonical_arm_identity_and_exhaustiveness():
    location = _loc()
    color = EnumDeclaration(
        "Color",
        (
            EnumVariant("Red", None, _loc(2)),
            EnumVariant("Blue", TypeRef(("Int",), _loc(3)), _loc(3)),
        ),
        location,
    )
    value = Identifier("value", _loc(6))
    red_body = Literal(1, _loc(10))
    blue_body = Identifier("n", _loc(14))
    match = MatchExpression(
        value,
        (
            MatchArm("Red", None, red_body, _loc(9)),
            MatchArm("Blue", "n", blue_body, _loc(13)),
        ),
        _loc(8),
    )
    function = FunctionDeclaration(
        "choose",
        (Parameter("value", TypeRef(("Color",), location), location),),
        TypeRef(("Int",), location),
        Block((ExpressionStatement(match, match.location),)),
        location,
    )
    program = Program((function,), enums=(color,))
    report = lower_typed_hir(program)

    facts = resolve_match_semantics_v1(program, report, match)

    assert facts.enum_identity == "Color"
    assert facts.exhaustive is True
    assert tuple(arm.variant_identity for arm in facts.arms) == (
        "Color::Red",
        "Color::Blue",
    )
    assert facts.arms[0].payload_type is None
    assert facts.arms[1].payload_type == INT


def test_duplicate_visible_variant_names_do_not_override_scrutinee_enum_identity():
    location = _loc()
    first = EnumDeclaration(
        "First",
        (EnumVariant("Same", None, _loc(2)),),
        location,
    )
    second = EnumDeclaration(
        "Second",
        (EnumVariant("Same", None, _loc(3)),),
        location,
    )
    value = Identifier("value", _loc(6))
    match = MatchExpression(
        value,
        (MatchArm("Same", None, Literal(1, _loc(10)), _loc(9)),),
        _loc(8),
    )
    function = FunctionDeclaration(
        "choose",
        (Parameter("value", TypeRef(("Second",), location), location),),
        TypeRef(("Int",), location),
        Block((ExpressionStatement(match, match.location),)),
        location,
    )
    program = Program((function,), enums=(first, second))
    report = lower_typed_hir(program)

    facts = resolve_match_semantics_v1(program, report, match)

    assert facts.enum_identity == "Second"
    assert facts.arms[0].variant_identity == "Second::Same"
    assert facts.exhaustive is True


def test_unresolved_arm_identity_fails_closed_in_exhaustiveness_fact():
    location = _loc()
    state = EnumDeclaration(
        "State",
        (EnumVariant("Ready", None, _loc(2)),),
        location,
    )
    value = Identifier("value", _loc(6))
    match = MatchExpression(
        value,
        (MatchArm("Unknown", None, Literal(1, _loc(10)), _loc(9)),),
        _loc(8),
    )
    function = FunctionDeclaration(
        "choose",
        (Parameter("value", TypeRef(("State",), location), location),),
        TypeRef(("Int",), location),
        Block((ExpressionStatement(match, match.location),)),
        location,
    )
    program = Program((function,), enums=(state,))
    report = lower_typed_hir(program)

    facts = resolve_match_semantics_v1(program, report, match)

    assert facts.arms[0].variant_identity is None
    assert facts.exhaustive is False
    assert facts.arms[0].payload_type is None
