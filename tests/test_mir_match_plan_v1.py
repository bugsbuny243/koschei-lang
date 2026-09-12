from dataclasses import replace

import pytest

from koschei.ast_nodes import (
    Identifier,
    Literal,
    MatchArm,
    MatchExpression,
    Program,
    SourceLocation,
)
from koschei.mir_match_plan_v1 import MirMatchPlanError, build_mir_match_plan_v1
from koschei.typed_hir import TypedHIRChecker
from koschei.type_system import INT, generic


def _loc() -> SourceLocation:
    return SourceLocation(1, 1)


def _resolved_option_match():
    loc = _loc()
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})
    expression = MatchExpression(
        Identifier("choice", loc),
        (
            MatchArm("Some", "payload", Identifier("payload", loc), loc),
            MatchArm("None", None, Literal(0, loc), loc),
        ),
        loc,
    )
    checker.infer(expression)
    return expression, checker.check()


def test_match_plan_uses_typed_hir_canonical_owner_identity():
    expression, report = _resolved_option_match()
    plan = build_mir_match_plan_v1(report, expression)
    assert [arm.canonical_variant for arm in plan.arms] == [
        "Option::Some",
        "Option::None",
    ]
    assert plan.arms[0].payload_required is True
    assert plan.arms[0].binding_name == "payload"
    assert plan.arms[1].payload_required is False
    assert plan.exhaustive is True
    assert plan.authority is False


def test_missing_typed_match_resolution_fails_closed():
    loc = _loc()
    expression = MatchExpression(
        Identifier("choice", loc),
        (MatchArm("Some", None, Literal(1, loc), loc),),
        loc,
    )
    empty = TypedHIRChecker(Program(())).check()
    with pytest.raises(MirMatchPlanError, match="lacks compiler-owned"):
        build_mir_match_plan_v1(empty, expression)


def test_visible_variant_name_cannot_replace_canonical_identity():
    expression, report = _resolved_option_match()
    resolution = report.match_resolution_of(expression)
    assert resolution is not None
    forged_arm = replace(resolution.arms[0], canonical_variant="Some")
    forged_resolution = replace(resolution, arms=(forged_arm, *resolution.arms[1:]))
    forged_report = replace(report, match_resolutions=(forged_resolution,))
    with pytest.raises(MirMatchPlanError, match="Owner::Variant"):
        build_mir_match_plan_v1(forged_report, expression)


def test_binding_without_payload_type_fails_closed():
    expression, report = _resolved_option_match()
    resolution = report.match_resolution_of(expression)
    assert resolution is not None
    broken_arm = replace(resolution.arms[0], payload_type=None, binding_type=None)
    broken_resolution = replace(resolution, arms=(broken_arm, *resolution.arms[1:]))
    broken_report = replace(report, match_resolutions=(broken_resolution,))
    with pytest.raises(MirMatchPlanError, match="payload-binding arm"):
        build_mir_match_plan_v1(broken_report, expression)


def test_arm_order_drift_is_rejected():
    expression, report = _resolved_option_match()
    resolution = report.match_resolution_of(expression)
    assert resolution is not None
    reversed_resolution = replace(resolution, arms=tuple(reversed(resolution.arms)))
    reversed_report = replace(report, match_resolutions=(reversed_resolution,))
    with pytest.raises(MirMatchPlanError, match="arm order"):
        build_mir_match_plan_v1(reversed_report, expression)
