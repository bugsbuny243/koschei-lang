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


def test_variant_construct_contract_seals_exact_identity_and_payload_ssa():
    location = SourceLocation(6, 2)
    instruction = MirVariantConstruct(10, "State::Ready", 9, INT, location)
    assert instruction_contract(instruction) == {
        "kind": "variantconstruct",
        "line": 6,
        "column": 2,
        "target": 10,
        "variant": "State::Ready",
        "source": 9,
        "type": "Int",
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


def test_variant_construct_payload_participates_in_canonical_ssa_validator():
    location = SourceLocation(1, 1)
    block = MirBasicBlock(
        0,
        (MirVariantConstruct(1, "State::Ready", 99, INT, location),),
        MirReturn(1),
    )
    try:
        validate_blocks((block,))
    except ValueError as error:
        assert "99" in str(error)
    else:
        raise AssertionError("variant constructor must not consume undefined payload SSA")
