from types import SimpleNamespace

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.mir_instruction_registry_v4 import (
    MIR_V4_INSTRUCTION_TYPES,
    is_mir_v4_instruction,
    require_mir_v4_graph_registry,
    require_mir_v4_instruction,
)
from koschei.mir_ir import MirConst
from koschei.type_system import INT


class ForgedMirConst(MirConst):
    pass


class UnknownInstruction:
    pass


def _graph_with(instruction):
    block = SimpleNamespace(instructions=(instruction,))
    function = SimpleNamespace(blocks=(block,))
    module = SimpleNamespace(functions=(function,))
    return SimpleNamespace(modules={"root": module})


def test_registry_has_no_duplicate_instruction_class_identity():
    assert len(MIR_V4_INSTRUCTION_TYPES) == len(set(MIR_V4_INSTRUCTION_TYPES))


def test_exact_registered_instruction_is_accepted():
    instruction = MirConst(0, 7, INT, SourceLocation(1, 1))
    assert is_mir_v4_instruction(instruction)
    require_mir_v4_instruction(instruction)
    require_mir_v4_graph_registry(_graph_with(instruction))


def test_unregistered_instruction_fails_closed():
    with pytest.raises(ValueError, match="unregistered MIR v4 instruction class"):
        require_mir_v4_instruction(UnknownInstruction())


def test_registered_instruction_subclass_cannot_inherit_opcode_authority():
    forged = ForgedMirConst(0, 7, INT, SourceLocation(1, 1))
    assert not is_mir_v4_instruction(forged)
    with pytest.raises(ValueError, match="ForgedMirConst"):
        require_mir_v4_graph_registry(_graph_with(forged))
