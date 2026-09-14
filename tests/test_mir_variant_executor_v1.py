from __future__ import annotations

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.interpreter import EnumValue
from koschei.mir_executor_v1 import MirExecutionError, MirExecutorV1
from koschei.mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from koschei.type_system import BOOL, INT


def _executor() -> MirExecutorV1:
    # Variant instructions are pure over their supplied SSA values and do not
    # consult executor graph/primitives. Bypass __init__ to isolate this boundary.
    return object.__new__(MirExecutorV1)


def test_variant_is_uses_exact_owner_and_variant_identity() -> None:
    location = SourceLocation(1, 1)
    values = {0: EnumValue("Alpha", "Ready", 7)}
    instruction = MirVariantIs(1, 0, "Alpha::Ready", BOOL, location)
    _executor()._execute_instruction("root", instruction, values, {})
    assert values[1] is True

    values = {0: EnumValue("Beta", "Ready", 7)}
    _executor()._execute_instruction("root", instruction, values, {})
    assert values[1] is False


def test_variant_payload_requires_exact_canonical_match() -> None:
    location = SourceLocation(1, 1)
    values = {0: EnumValue("Result", "Ok", 41)}
    instruction = MirVariantPayload(1, 0, "Result::Ok", INT, location)
    _executor()._execute_instruction("root", instruction, values, {})
    assert values[1] == 41


def test_variant_payload_fails_closed_for_wrong_owner() -> None:
    location = SourceLocation(1, 1)
    values = {0: EnumValue("Other", "Ok", 41)}
    instruction = MirVariantPayload(1, 0, "Result::Ok", INT, location)
    with pytest.raises(MirExecutionError, match="failed closed"):
        _executor()._execute_instruction("root", instruction, values, {})


def test_variant_instructions_reject_non_enum_host_shape() -> None:
    class FakeEnum:
        enum_name = "Result"
        variant = "Ok"
        payload = 41

    location = SourceLocation(1, 1)
    values = {0: FakeEnum()}
    instruction = MirVariantIs(1, 0, "Result::Ok", BOOL, location)
    with pytest.raises(MirExecutionError, match="failed closed"):
        _executor()._execute_instruction("root", instruction, values, {})
