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
    MirMapContains,
    MirMapGet,
    MirMapInsert,
    MirMapKeys,
    MirMapSet,
    MirUnit,
    MirVariantConstruct,
    MirVariantIs,
    MirVariantPayload,
)
from koschei.mir_instruction_registry_v4 import (
    MIR_V4_EXTENSION_INSTRUCTION_TYPES as RegistryExtensionTypes,
    is_mir_v4_extension_instruction,
)
from koschei.mir_ir import instruction_contract, validate_blocks, MirBasicBlock, MirReturn
from koschei.mir_or_return_normalization_v1 import (
    MirFallibleIsSuccess as CompatMirFallibleIsSuccess,
    MirInterpolate as CompatMirInterpolate,
)
from koschei.type_system import BOOL, INT, STRING, VOID


def test_compatibility_modules_reexport_exact_canonical_class_objects():
    assert CompatMirIsRuntimeError is MirIsRuntimeError
    assert CompatMirMapInsert is MirMapInsert
    assert CompatMirFallibleIsSuccess is MirFallibleIsSuccess
    assert CompatMirInterpolate is MirInterpolate


def test_extension_instruction_authority_has_no_duplicate_class_names():
    names = [item.__name__ for item in MIR_V4_EXTENSION_INSTRUCTION_TYPES]
    assert len(names) == len(set(names))
    assert set(names) == {
        "MirUnit",
        "MirFallibleIsSuccess",
        "MirFalliblePayload",
        "MirInterpolate",
        "MirIsRuntimeError",
        "MirVariantConstruct",
        "MirVariantIs",
        "MirVariantPayload",
        "MirCapabilityCall",
        "MirMapNew",
        "MirMapInsert",
        "MirMapFinish",
        "MirMapGet",
        "MirMapSet",
        "MirMapKeys",
        "MirMapContains",
        "MirStructNew",
        "MirStructSet",
        "MirStructFinish",
        "MirStructFieldSet",
    }


def test_v4_registry_reuses_extension_authority_instead_of_copying_it():
    assert RegistryExtensionTypes is MIR_V4_EXTENSION_INSTRUCTION_TYPES
    location = SourceLocation(2, 4)
    assert is_mir_v4_extension_instruction(
        MirInterpolate(3, (1, 2), STRING, location)
    )
    assert is_mir_v4_extension_instruction(MirUnit(4, VOID, location))
    assert is_mir_v4_extension_instruction(
        MirVariantConstruct(5, "Option::Some", 4, INT, location)
    )
    assert is_mir_v4_extension_instruction(
        MirVariantIs(6, 5, "Option::Some", BOOL, location)
    )
    assert is_mir_v4_extension_instruction(
        MirVariantPayload(7, 5, "Option::Some", STRING, location)
    )


def test_unit_instruction_contract_is_canonical_and_host_opaque():
    location = SourceLocation(5, 6)
    assert instruction_contract(MirUnit(8, VOID, location)) == {
        "kind": "unit",
        "line": 5,
        "column": 6,
        "target": 8,
        "type": "Void",
    }


def test_validate_blocks_accepts_extension_instructions_from_canonical_authority():
    location = SourceLocation(8, 2)
    blocks = (
        MirBasicBlock(
            id=0,
            instructions=(MirUnit(1, VOID, location),),
            terminator=MirReturn(1, location),
        ),
    )
    validate_blocks(blocks)
