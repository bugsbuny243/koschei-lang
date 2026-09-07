from koschei.ast_nodes import SourceLocation
from koschei.mir_container_staging_v1 import (
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
)
from koschei.mir_ir import MirBasicBlock, MirReturn, validate_blocks
from koschei.type_system import BOOL, UnknownType


def test_runtime_error_check_is_distinct_from_general_fallible_unwrap() -> None:
    location = SourceLocation(1, 1)
    instruction = MirIsRuntimeError(2, 1, BOOL, location)
    assert instruction.source == 1
    assert instruction.target == 2


def test_map_staging_uses_existing_object_arguments_source_ssa_contract() -> None:
    location = SourceLocation(2, 3)
    map_type = UnknownType()
    create = MirMapNew(0, map_type, location)
    insert = MirMapInsert(0, (1, 2), map_type, location)
    finish = MirMapFinish(3, 0, map_type, location)

    assert create.target == insert.object
    assert insert.arguments == (1, 2)
    assert finish.source == create.target


def test_struct_staging_uses_existing_object_source_ssa_contract() -> None:
    location = SourceLocation(4, 5)
    struct_type = UnknownType()
    create = MirStructNew(0, "Profile", struct_type, location)
    assign = MirStructSet(0, "name", 1, struct_type, location)
    finish = MirStructFinish(2, 0, struct_type, location)

    assert create.type_name == "Profile"
    assert assign.object == create.target
    assert assign.source == 1
    assert finish.source == create.target


def test_existing_mir_validator_tracks_container_ssa_uses() -> None:
    location = SourceLocation(1, 1)
    unknown = UnknownType()
    blocks = (
        MirBasicBlock(
            0,
            (
                MirMapNew(0, unknown, location),
                MirMapInsert(0, (1, 2), unknown, location),
                MirMapFinish(3, 0, unknown, location),
            ),
            MirReturn(3),
        ),
    )

    try:
        validate_blocks(blocks)
    except ValueError as error:
        assert "undefined values" in str(error)
        assert "1" in str(error) and "2" in str(error)
    else:
        raise AssertionError("container key/value SSA must be tracked by canonical MIR validator")


def test_staged_container_nodes_have_no_authority_or_ast_payload_fields() -> None:
    location = SourceLocation(1, 1)
    nodes = (
        MirMapNew(0, UnknownType(), location),
        MirMapInsert(0, (1, 2), UnknownType(), location),
        MirMapFinish(3, 0, UnknownType(), location),
        MirStructNew(0, "Profile", UnknownType(), location),
        MirStructSet(0, "name", 3, UnknownType(), location),
        MirStructFinish(4, 0, UnknownType(), location),
    )
    for node in nodes:
        assert not hasattr(node, "authority")
        assert not hasattr(node, "ast")
        assert not hasattr(node, "expression")
