from __future__ import annotations

from koschei.ast_nodes import SourceLocation
from koschei.interpreter import EnumValue
from koschei.mir_extension_instructions_v4 import (
    MirFallibleIsSuccess,
    MirFalliblePayload,
    MirInterpolate,
    MirIsRuntimeError,
    MirUnit,
)
from koschei.mir_native_runtime import (
    MirNativeRuntimeError,
    _ErrorValue,
    _MirExecutor,
    _UNIT,
)
from koschei.type_system import BOOL, INT, STRING, VOID


LOC = SourceLocation(1, 1)


def _run(instructions, initial=None):
    executor = object.__new__(_MirExecutor)
    values = dict(initial or {})
    environment = {}
    mutable = set()
    for instruction in instructions:
        executor._execute_instruction(instruction, values, environment, mutable, "root")
    return values


def test_unit_is_a_canonical_runtime_value():
    values = _run((MirUnit(1, VOID, LOC),))
    assert values[1] is _UNIT


def test_runtime_error_probe_is_explicit():
    values = _run(
        (
            MirIsRuntimeError(2, 1, BOOL, LOC),
            MirIsRuntimeError(4, 3, BOOL, LOC),
        ),
        {1: _ErrorValue("boom"), 3: 7},
    )
    assert values[2] is True
    assert values[4] is False


def test_option_and_result_success_projection_matches_language_contract():
    values = _run(
        (
            MirFallibleIsSuccess(3, 1, BOOL, LOC),
            MirFalliblePayload(4, 1, INT, LOC),
            MirFallibleIsSuccess(5, 2, BOOL, LOC),
        ),
        {
            1: EnumValue("Option", "Some", 7),
            2: EnumValue("Option", "None"),
        },
    )
    assert values[3] is True
    assert values[4] == 7
    assert values[5] is False


def test_error_value_is_not_a_fallible_success():
    values = _run(
        (MirFallibleIsSuccess(2, 1, BOOL, LOC),),
        {1: _ErrorValue("missing")},
    )
    assert values[2] is False


def test_payload_without_success_proof_fails_closed():
    try:
        _run(
            (MirFalliblePayload(2, 1, INT, LOC),),
            {1: EnumValue("Result", "Err", "bad")},
        )
    except MirNativeRuntimeError as error:
        assert "success proof" in str(error)
    else:
        raise AssertionError("fallible payload must fail closed on Err")


def test_interpolation_uses_koschei_rendering():
    values = _run(
        (MirInterpolate(3, (1, 2), STRING, LOC),),
        {1: "n=", 2: 7},
    )
    assert values[3] == "n=7"
