from koschei.ast_nodes import SourceLocation
from koschei.mir_container_staging_v1 import (
    MirIsRuntimeError as CompatMirIsRuntimeError,
    MirMapInsert as CompatMirMapInsert,
)
from koschei.mir_extension_instructions_v4 import (
    MIR_V4_EXTENSION_INSTRUCTION_TYPES,
    MirFallibleIsSuccess,
    MirInterpolate,
    MirIsRuntimeError,
    MirMapInsert,
)
from koschei.mir_ir import instruction_contract, validate_blocks, MirBasicBlock, MirReturn
from koschei.mir_or_return_normalization_v1 import (
    MirFallibleIsSuccess as CompatMirFallibleIsSuccess,
    MirInterpolate as CompatMirInterpolate,
)
from koschei.type_system import BOOL, STRING


def test_compatibility_modules_reexport_exact_canonical_class_objects():
    assert CompatMirIsRuntimeError is MirIsRuntimeError
    assert CompatMirMapInsert is MirMapInsert
    assert CompatMirFallibleIsSuccess is MirFallibleIsSuccess
    assert CompatMirInterpolate is MirInterpolate


def test_extension_instruction_authority_has_no_duplicate_class_names():
    names = [item.__name__ for item in MIR_V4_EXTENSION_INSTRUCTION_TYPES]
    assert len(names) == len(set(names))
    assert set(names) == {
        "MirFallibleIsSuccess",
        "MirFalliblePayload",
        "MirInterpolate",
        "MirIsRuntimeError",
        "MirMapNew",
        "MirMapInsert",
        "MirMapFinish",
        "MirStructNew",
        "MirStructSet",
        "MirStructFinish",
    }


def test_extension_instruction_contract_uses_existing_canonical_serializer():
    location = SourceLocation(7, 3)
    instruction = MirInterpolate(9, (1, 2), STRING, location)
    assert instruction_contract(instruction) == {
        "kind": "interpolate",
        "line": 7,
        "column": 3,
        "target": 9,
        "items": (1, 2),
        "type": "String",
    }


def test_container_extension_fields_participate_in_canonical_ssa_validator():
    location = SourceLocation(1, 1)
    block = MirBasicBlock(
        0,
        (
            MirIsRuntimeError(0, 41, BOOL, location),
            MirMapInsert(0, (42, 43), STRING, location),
        ),
        MirReturn(None),
    )
    try:
        validate_blocks((block,))
    except ValueError as error:
        message = str(error)
        assert "41" in message
        assert "42" in message
        assert "43" in message
    else:
        raise AssertionError("canonical validator must reject undefined extension SSA uses")
