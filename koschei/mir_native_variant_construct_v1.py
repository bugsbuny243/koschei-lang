"""Narrow native-MIR extension for canonical variant construction.

This module does not fork the native runtime. It delegates every existing MIR
instruction and execution rule to :mod:`koschei.mir_native_runtime` and adds only
``MirVariantConstruct`` plus the admission checks needed to make enum values
materialize from an already-sealed ``Owner::Variant`` identity.
"""
from __future__ import annotations

from typing import Any

from .interpreter import EnumValue
from .mir_extension_instructions_v4 import MirVariantConstruct
from .mir_native_runtime import (
    MirNativeCallDepthExceeded,
    MirNativeProgramError,
    MirNativeRuntimeError,
    MirNativeStepBudgetExceeded,
    MirNativeSupport,
    MirNativeUnsupported,
    _ErrorValue,
    _MirExecutor,
    _MAX_CALL_DEPTH,
    _DEFAULT_MAX_STEPS,
    inspect_native_mir_support as _inspect_base,
)
from .mir_variant_runtime_v1 import MirVariantRuntimeError, split_canonical_variant_v1


def _enum_declarations_by_owner(mir) -> dict[str, list[object]]:
    result: dict[str, list[object]] = {}
    for module in mir.in_dependency_order():
        for declaration in module.program.enums:
            result.setdefault(declaration.name, []).append(declaration)
    return result


def _validate_variant_constructs_v1(mir) -> tuple[str, ...]:
    reasons: list[str] = []
    declarations = _enum_declarations_by_owner(mir)
    builtin_variants = {
        "Option": {"Some": True, "None": False},
        "Result": {"Ok": True, "Err": True},
    }

    for module in mir.in_dependency_order():
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    if not isinstance(instruction, MirVariantConstruct):
                        continue
                    label = f"{module.name}.{function.name}"
                    try:
                        owner, variant = split_canonical_variant_v1(instruction.variant)
                    except MirVariantRuntimeError as exc:
                        reasons.append(f"{label}: invalid canonical constructor identity: {exc}")
                        continue

                    builtin = builtin_variants.get(owner)
                    if builtin is not None:
                        expects_payload = builtin.get(variant)
                        if expects_payload is None:
                            reasons.append(
                                f"{label}: unknown builtin canonical variant {instruction.variant}"
                            )
                            continue
                        if expects_payload != (instruction.source is not None):
                            reasons.append(
                                f"{label}: builtin constructor payload shape drifted for "
                                f"{instruction.variant}"
                            )
                        continue

                    candidates = declarations.get(owner, [])
                    if len(candidates) != 1:
                        reasons.append(
                            f"{label}: canonical enum owner {owner!r} is not globally unique"
                        )
                        continue
                    declaration = candidates[0]
                    target = next(
                        (item for item in declaration.variants if item.name == variant),
                        None,
                    )
                    if target is None:
                        reasons.append(
                            f"{label}: canonical enum variant {instruction.variant!r} "
                            "is absent from the checked declaration"
                        )
                        continue
                    expects_payload = target.payload_type is not None
                    if expects_payload != (instruction.source is not None):
                        reasons.append(
                            f"{label}: constructor payload shape drifted for "
                            f"{instruction.variant}"
                        )
    return tuple(dict.fromkeys(reasons))


def inspect_native_mir_support(mir) -> MirNativeSupport:
    """Extend base native admission only for sealed canonical enum construction."""

    base = _inspect_base(mir)
    reasons: list[str] = []
    for reason in base.reasons:
        if reason.endswith("native MIR v1 does not execute enums yet"):
            continue
        if reason.endswith("unsupported MIR instruction MirVariantConstruct"):
            continue
        reasons.append(reason)
    reasons.extend(_validate_variant_constructs_v1(mir))
    return MirNativeSupport(not reasons, tuple(dict.fromkeys(reasons)))


class _VariantConstructExecutor(_MirExecutor):
    def _execute_instruction(
        self,
        instruction: Any,
        values: dict[int, Any],
        environment: dict[str, Any],
        mutable: set[str],
        module_key: str,
    ) -> None:
        if isinstance(instruction, MirVariantConstruct):
            try:
                owner, variant = split_canonical_variant_v1(instruction.variant)
            except MirVariantRuntimeError as exc:
                raise MirNativeRuntimeError(
                    f"MIR variant construction failed closed: {exc}"
                ) from exc
            if instruction.source is None:
                values[instruction.target] = EnumValue(owner, variant)
            else:
                values[instruction.target] = EnumValue(
                    owner,
                    variant,
                    self._value(values, instruction.source),
                )
            return
        super()._execute_instruction(
            instruction,
            values,
            environment,
            mutable,
            module_key,
        )


def run_mir_native(
    mir,
    *,
    max_steps: int = _DEFAULT_MAX_STEPS,
    max_call_depth: int = _MAX_CALL_DEPTH,
) -> int:
    """Execute admitted MIR using the base runtime plus variant construction."""

    support = inspect_native_mir_support(mir)
    if not support.supported:
        raise MirNativeUnsupported("; ".join(support.reasons))
    if max_steps <= 0:
        raise ValueError("max_steps must be a positive integer")
    if max_call_depth <= 0 or max_call_depth > _MAX_CALL_DEPTH:
        raise ValueError(f"max_call_depth must be between 1 and {_MAX_CALL_DEPTH}")
    executor = _VariantConstructExecutor(
        mir,
        max_steps=max_steps,
        max_call_depth=max_call_depth,
    )
    result = executor.execute_main()
    if isinstance(result, _ErrorValue):
        raise MirNativeProgramError(result.message)
    return 0


__all__ = [
    "MirNativeCallDepthExceeded",
    "MirNativeProgramError",
    "MirNativeRuntimeError",
    "MirNativeStepBudgetExceeded",
    "inspect_native_mir_support",
    "run_mir_native",
]
