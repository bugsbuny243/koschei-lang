"""Compiler-owned MatchExpression lowering plan for MIR v4.

This module converts Typed-HIR match resolution into a representation-only plan.
It carries no authority and never inspects runtime objects or source-visible names
as canonical identity. The actual lowerer must consume this plan exactly.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import MatchExpression
from .type_system import TypeNode
from .typed_hir import TypedHIRReport, TypedMatchArmResolution


class MirMatchPlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MirMatchArmPlanV1:
    canonical_variant: str
    binding_name: str | None
    binding_type: TypeNode | None
    payload_required: bool


@dataclass(frozen=True, slots=True)
class MirMatchPlanV1:
    arms: tuple[MirMatchArmPlanV1, ...]
    exhaustive: bool
    authority: bool = False

    def assert_valid(self) -> None:
        if self.authority:
            raise MirMatchPlanError("match lowering plan is not an authority credential")
        if not self.arms:
            raise MirMatchPlanError("match lowering plan requires at least one arm")
        identities = [arm.canonical_variant for arm in self.arms]
        if len(identities) != len(set(identities)):
            raise MirMatchPlanError("duplicate canonical match arm identity")
        for arm in self.arms:
            owner, sep, variant = arm.canonical_variant.partition("::")
            if sep != "::" or not owner or not variant or "::" in variant:
                raise MirMatchPlanError("match arm identity must be canonical Owner::Variant")
            if arm.payload_required != (arm.binding_name is not None):
                raise MirMatchPlanError("payload extraction must match lexical binding presence")
            if arm.binding_name is None and arm.binding_type is not None:
                raise MirMatchPlanError("unbound match arm cannot carry a binding type")


def _arm_plan(arm: TypedMatchArmResolution) -> MirMatchArmPlanV1:
    if arm.arm.binding is None:
        if arm.binding_type is not None:
            raise MirMatchPlanError("Typed-HIR emitted binding type for unbound match arm")
        return MirMatchArmPlanV1(
            canonical_variant=arm.canonical_variant,
            binding_name=None,
            binding_type=None,
            payload_required=False,
        )
    if arm.payload_type is None or arm.binding_type is None:
        raise MirMatchPlanError("payload-binding arm lacks compiler-owned payload type")
    return MirMatchArmPlanV1(
        canonical_variant=arm.canonical_variant,
        binding_name=arm.arm.binding,
        binding_type=arm.binding_type,
        payload_required=True,
    )


def build_mir_match_plan_v1(
    typed_report: TypedHIRReport,
    expression: MatchExpression,
) -> MirMatchPlanV1:
    """Build exact lowering facts from the one Typed-HIR match authority.

    Missing resolution is a hard failure. MIR must not guess owner, payload type,
    arm order, or exhaustiveness from AST text or runtime declarations.
    """

    resolution = typed_report.match_resolution_of(expression)
    if resolution is None:
        raise MirMatchPlanError("MatchExpression lacks compiler-owned Typed-HIR resolution")
    if tuple(item.arm for item in resolution.arms) != tuple(expression.arms):
        raise MirMatchPlanError("Typed-HIR match arm order/identity drift")
    plan = MirMatchPlanV1(
        arms=tuple(_arm_plan(item) for item in resolution.arms),
        exhaustive=resolution.exhaustive,
    )
    plan.assert_valid()
    return plan


__all__ = [
    "MirMatchArmPlanV1",
    "MirMatchPlanError",
    "MirMatchPlanV1",
    "build_mir_match_plan_v1",
]
