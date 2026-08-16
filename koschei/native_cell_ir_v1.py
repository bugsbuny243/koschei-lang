"""Koschei Native Cell Reality -> Native IR bridge v1.

The authenticated cell/projection frontend remains responsible for proving the
complete sealed schema. This module only changes what happens after that proof:
the selected scalar becomes a Koschei Native IR atom instead of being wrapped in
the legacy Program/function/return compatibility AST.
"""

from __future__ import annotations

from dataclasses import dataclass

from .native_cell_projection_v1 import NativeCellProjectionCheckV1
from .native_conduit_ir_v1 import lower_conduit_source_to_native_ir_v1
from .native_ir_v1 import NativeIrAtomV1, NativeIrRealityV1, NativeIrWitnessV1, execute_native_ir_v1
from .native_value_domains_v1 import NativeValue


class NativeCellIrError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NativeCellIrProjectionV1:
    schema_id: bytes
    selected_ordinal: int
    selected_value: NativeValue
    ir: NativeIrRealityV1


def lower_checked_cell_projection_to_native_ir_v1(
    checked: NativeCellProjectionCheckV1,
) -> NativeCellIrProjectionV1:
    """Carry one already-proven cell scalar into Native IR.

    Full-schema validation MUST happen before this function. We deliberately
    accept only NativeCellProjectionCheckV1, not a raw value + loose ordinal pair.
    """
    if not isinstance(checked, NativeCellProjectionCheckV1):
        raise NativeCellIrError("cell Native IR lowering requires an authenticated projection check")
    if not isinstance(checked.schema_id, bytes) or len(checked.schema_id) != 16 or not any(checked.schema_id):
        raise NativeCellIrError("cell Native IR projection has invalid sealed schema identity")
    if not 0 <= checked.selected_ordinal < len(checked.cells):
        raise NativeCellIrError("cell Native IR projection ordinal is outside the proven schema")
    if checked.cells[checked.selected_ordinal] != checked.selected_value:
        raise NativeCellIrError("selected cell value disagrees with the proven full schema")

    witness = NativeIrWitnessV1(
        name="cellreality",
        operation=None,
        atoms=(NativeIrAtomV1(literal=checked.selected_value),),
    )
    ir = NativeIrRealityV1((witness,), "cellreality")
    return NativeCellIrProjectionV1(
        schema_id=checked.schema_id,
        selected_ordinal=checked.selected_ordinal,
        selected_value=checked.selected_value,
        ir=ir,
    )


def execute_checked_cell_projection_native_ir_v1(
    checked: NativeCellProjectionCheckV1,
) -> NativeValue:
    projected = lower_checked_cell_projection_to_native_ir_v1(checked)
    return execute_native_ir_v1(projected.ir)


def feed_checked_cell_projection_to_conduit_ir_v1(
    checked: NativeCellProjectionCheckV1,
    *,
    source: str,
    slot: int = 0,
) -> NativeIrRealityV1:
    """Bind a proven cell scalar to one sealed conduit slot in Native IR.

    No member/index syntax or function parameter object is synthesized. The cell
    ordinal remains authenticated projection metadata; the reusable source sees
    only its local conduit slot.
    """
    projected = lower_checked_cell_projection_to_native_ir_v1(checked)
    value = execute_native_ir_v1(projected.ir)
    return lower_conduit_source_to_native_ir_v1(source, {slot: value})
