from koschei.ast_nodes import SourceLocation
from koschei.mir_container_staging_v1 import (
    MirIsRuntimeError,
    MirMapInsert,
    MirMapNew,
    MirStructNew,
    MirStructSet,
)
from koschei.type_system import BOOL, UnknownType


def test_runtime_error_check_is_distinct_from_general_fallible_unwrap() -> None:
    location = SourceLocation(1, 1)
    instruction = MirIsRuntimeError(2, 1, BOOL, location)

    assert instruction.source == 1
    assert instruction.target == 2
    assert instruction.type == BOOL


def test_map_staging_separates_construction_from_single_entry_commit() -> None:
    location = SourceLocation(2, 3)
    map_type = UnknownType()
    create = MirMapNew(0, map_type, location)
    insert = MirMapInsert(0, 1, 2, map_type, location)

    assert create.target == insert.container
    assert insert.key == 1
    assert insert.value == 2


def test_struct_staging_carries_compiler_checked_identity_per_field() -> None:
    location = SourceLocation(4, 5)
    struct_type = UnknownType()
    create = MirStructNew(0, "Profile", struct_type, location)
    assign = MirStructSet(0, "name", 3, struct_type, location)

    assert create.type_name == "Profile"
    assert assign.container == create.target
    assert assign.field == "name"


def test_staged_container_nodes_have_no_authority_or_ast_payload_fields() -> None:
    location = SourceLocation(1, 1)
    nodes = (
        MirMapNew(0, UnknownType(), location),
        MirMapInsert(0, 1, 2, UnknownType(), location),
        MirStructNew(0, "Profile", UnknownType(), location),
        MirStructSet(0, "name", 3, UnknownType(), location),
    )

    for node in nodes:
        assert not hasattr(node, "authority")
        assert not hasattr(node, "ast")
        assert not hasattr(node, "expression")
