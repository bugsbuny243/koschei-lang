from __future__ import annotations

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.mir_extension_instructions_v4 import (
    MIR_V4_EXTENSION_INSTRUCTION_TYPES,
    MirVariantIs,
    MirVariantPayload,
)
from koschei.mir_ir import (
    MirBasicBlock,
    MirBranch,
    MirConst,
    MirJump,
    MirReturn,
    validate_blocks,
)
from koschei.mir_variant_proof_v1 import validate_variant_proofs_v1
from koschei.type_system import BOOL, INT


def _loc() -> SourceLocation:
    return SourceLocation(1, 1)


def _proven_blocks(payload_variant: str = "Choice::Some"):
    location = _loc()
    return (
        MirBasicBlock(
            0,
            (
                MirConst(0, "enum-sentinel", INT, location),
                MirVariantIs(1, 0, "Choice::Some", BOOL, location),
            ),
            MirBranch(1, 1, 2),
        ),
        MirBasicBlock(
            1,
            (MirVariantPayload(2, 0, payload_variant, INT, location),),
            MirReturn(2),
        ),
        MirBasicBlock(2, (), MirReturn(0)),
    )


def test_variant_instructions_are_exact_v4_extension_authority_members():
    assert MirVariantIs in MIR_V4_EXTENSION_INSTRUCTION_TYPES
    assert MirVariantPayload in MIR_V4_EXTENSION_INSTRUCTION_TYPES


def test_variant_source_participates_in_existing_ssa_validation():
    location = _loc()
    blocks = (
        MirBasicBlock(
            0,
            (MirVariantIs(0, 99, "Choice::Some", BOOL, location),),
            MirReturn(0),
        ),
    )

    with pytest.raises(ValueError, match="undefined values"):
        validate_blocks(blocks)


def test_payload_is_allowed_only_on_matching_true_edge():
    blocks = _proven_blocks()

    # Canonical MIR validation owns both structural SSA and variant-path proof.
    validate_blocks(blocks)
    validate_variant_proofs_v1(blocks)


def test_canonical_gate_rejects_different_variant_than_predecessor_proof():
    blocks = _proven_blocks("Choice::None")

    with pytest.raises(ValueError, match="lacks exact proven predecessor path"):
        validate_blocks(blocks)


def test_canonical_gate_loses_payload_proof_at_ambiguous_cfg_join():
    location = _loc()
    blocks = (
        MirBasicBlock(
            0,
            (
                MirConst(0, "enum-sentinel", INT, location),
                MirVariantIs(1, 0, "Choice::Some", BOOL, location),
            ),
            MirBranch(1, 1, 2),
        ),
        MirBasicBlock(1, (), MirJump(3)),
        MirBasicBlock(2, (), MirJump(3)),
        MirBasicBlock(
            3,
            (MirVariantPayload(2, 0, "Choice::Some", INT, location),),
            MirReturn(2),
        ),
    )

    with pytest.raises(ValueError, match="lacks exact proven predecessor path"):
        validate_blocks(blocks)


def test_canonical_gate_rejects_non_dominating_test_target():
    location = _loc()
    blocks = (
        MirBasicBlock(
            0,
            (MirConst(0, "enum-sentinel", INT, location),),
            MirJump(2),
        ),
        MirBasicBlock(
            1,
            (MirVariantIs(1, 0, "Choice::Some", BOOL, location),),
            MirReturn(1),
        ),
        MirBasicBlock(2, (), MirBranch(1, 3, 4)),
        MirBasicBlock(
            3,
            (MirVariantPayload(2, 0, "Choice::Some", INT, location),),
            MirReturn(2),
        ),
        MirBasicBlock(4, (), MirReturn(0)),
    )

    # Global definition/use alone would admit %1 here. Canonical validation
    # must not turn that non-dominating value into payload authority.
    with pytest.raises(ValueError, match="lacks exact proven predecessor path"):
        validate_blocks(blocks)


def test_canonical_gate_rejects_visible_variant_name_without_owner_identity():
    location = _loc()
    blocks = (
        MirBasicBlock(
            0,
            (
                MirConst(0, "enum-sentinel", INT, location),
                MirVariantIs(1, 0, "Some", BOOL, location),
            ),
            MirBranch(1, 1, 2),
        ),
        MirBasicBlock(1, (), MirReturn(0)),
        MirBasicBlock(2, (), MirReturn(0)),
    )

    with pytest.raises(ValueError, match="canonical Owner::Variant"):
        validate_blocks(blocks)
