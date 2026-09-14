"""Explicit MIR v4 CFG lowering for compiler-resolved MatchExpression.

This helper is intentionally narrow: it consumes ``MirMatchPlanV1`` built from
Typed-HIR and drives the existing function lowerer interface.  It never resolves
variant owners, payload types, arm order, or exhaustiveness from AST/runtime
shape.
"""
from __future__ import annotations

from .ast_nodes import MatchExpression
from .mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from .mir_ir import MirBind, MirBranch, MirJump, MirLoad, MirUnreachable
from .mir_match_plan_v1 import MirMatchPlanError, build_mir_match_plan_v1
from .type_system import BOOL


def lower_match_expression_v1(lowerer, expression: MatchExpression) -> int:
    """Lower one compiler-resolved match into explicit test/payload/result CFG.

    Required lowerer surface is the canonical internal MIR lowerer surface:
    ``_lower_expression``, ``_new_value``, ``_new_block``, ``_emit``,
    ``_terminate``, ``_new_binding_name``, ``_new_internal_binding_name``,
    ``_type_of``, plus ``current``, ``blocks`` and ``scopes``.
    """

    plan = build_mir_match_plan_v1(lowerer.typed_report, expression)
    if not plan.exhaustive:
        raise MirMatchPlanError(
            "non-exhaustive MatchExpression cannot become executable canonical MIR"
        )

    # Evaluate the scrutinee exactly once. Every arm test and payload extraction
    # refers to this same SSA identity.
    scrutinee = lowerer._lower_expression(expression.value)
    result_type = lowerer._type_of(expression)
    result_name = lowerer._new_internal_binding_name("match_result")
    join_block = lowerer._new_block()

    for index, (source_arm, arm_plan) in enumerate(zip(expression.arms, plan.arms)):
        test = lowerer._new_value()
        lowerer._emit(
            MirVariantIs(
                test,
                scrutinee,
                arm_plan.canonical_variant,
                BOOL,
                source_arm.location,
            )
        )
        arm_block = lowerer._new_block()
        is_last = index == len(plan.arms) - 1
        miss_block = lowerer._new_block()
        lowerer._terminate(MirBranch(test, arm_block, miss_block))

        lowerer.current = arm_block
        lowerer.scopes.append({})
        try:
            if arm_plan.payload_required:
                if arm_plan.binding_name is None or arm_plan.binding_type is None:
                    raise MirMatchPlanError(
                        "payload arm lost compiler-owned binding contract"
                    )
                payload = lowerer._new_value()
                lowerer._emit(
                    MirVariantPayload(
                        payload,
                        scrutinee,
                        arm_plan.canonical_variant,
                        arm_plan.binding_type,
                        source_arm.location,
                    )
                )
                internal_name = lowerer._new_binding_name(arm_plan.binding_name)
                lowerer._emit(
                    MirBind(
                        internal_name,
                        payload,
                        False,
                        arm_plan.binding_type,
                        source_arm.location,
                    )
                )

            arm_value = lowerer._lower_expression(source_arm.body)
            if lowerer.blocks[lowerer.current].terminator is not None:
                raise MirMatchPlanError(
                    "match arm expression unexpectedly terminated control flow"
                )
            lowerer._emit(
                MirBind(
                    result_name,
                    arm_value,
                    False,
                    result_type,
                    source_arm.location,
                )
            )
            lowerer._terminate(MirJump(join_block))
        finally:
            lowerer.scopes.pop()

        lowerer.current = miss_block
        if is_last:
            # This edge is impossible only because Typed-HIR proved the exact arm
            # set exhaustive. Runtime/backends are forbidden from inventing a
            # default arm or re-resolving source-visible variant text.
            lowerer._terminate(
                MirUnreachable("compiler-proven exhaustive match had no variant arm")
            )

    lowerer.current = join_block
    target = lowerer._new_value()
    lowerer._emit(MirLoad(target, result_name, result_type, expression.location))
    return target


__all__ = ["lower_match_expression_v1"]
