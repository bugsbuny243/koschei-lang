from __future__ import annotations

from dataclasses import dataclass

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.mir_ir import MirBasicBlock, MirReturn, validate_blocks
from koschei.type_system import INT, TypeNode


@dataclass(frozen=True, slots=True)
class ForgedInstruction:
    target: int
    type: TypeNode
    location: SourceLocation


def test_unregistered_dataclass_instruction_is_rejected_at_block_validation() -> None:
    location = SourceLocation(1, 1)
    block = MirBasicBlock(
        0,
        (ForgedInstruction(0, INT, location),),
        MirReturn(0),
    )

    with pytest.raises(ValueError, match="unregistered MIR v4 instruction class"):
        validate_blocks((block,))
