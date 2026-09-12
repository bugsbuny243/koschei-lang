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

    validate_blocks(blocks)
    validate_variant_proofs_v1(blocks)


def test_payload_rejects_different_variant_than_predecessor_proof():
    blocks = _proven_blocks("Choice::None")

    validate_blocks(blocks)
    with pytest.raises(ValueError, match="lacks exact proven predecessor path"):
        validate_variant_proofs_v1(blocks)


def test_payload_proof_is_lost_at_ambiguous_cfg_join():
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

    validate_blocks(blocks)
    with pytest.raises(ValueError, match="lacks exact proven predecessor path"):
        validate_variant_proofs_v1(blocks)


def test_visible_variant_name_without_owner_identity_fails_closed():
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

    validate_blocks(blocks)
    with pytest.raises(ValueError, match="canonical Owner::Variant"):
        validate_variant_proofs_v1(blocks)
