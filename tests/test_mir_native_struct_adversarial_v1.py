from __future__ import annotations

import unittest
from koschei.mir_extension_instructions_v4 import MirStructFinish, MirStructNew, MirStructSet
from koschei.mir_ir import MirConst, MirMember
from koschei.mir_native_runtime import MirNativeRuntimeError, _MirExecutor, _StructValue
from koschei.type_system import INT, NamedType
from koschei.ast_nodes import SourceLocation


LOC = SourceLocation(1, 1)
ACCOUNT = NamedType("Account")


def _executor():
    executor = object.__new__(_MirExecutor)
    # Struct/const transitions do not consult graph/module state. Keep this
    # harness deliberately minimal so the observed result comes from the real
    # executor instruction implementation, not from a mocked semantic layer.
    return executor


def _run(instructions):
    executor = _executor()
    values = {}
    environment = {}
    mutable = set()
    for instruction in instructions:
        executor._execute_instruction(instruction, values, environment, mutable, "root")
    return values


class NativeMirStructAdversarialTests(unittest.TestCase):
    def test_exact_struct_executes_through_real_instruction_path(self):
        values = _run((
            MirStructNew(1, "Account", ("id", "balance"), ACCOUNT, LOC),
            MirConst(2, 7, INT, LOC),
            MirStructSet(1, "id", 2, ACCOUNT, LOC),
            MirConst(3, 9, INT, LOC),
            MirStructSet(1, "balance", 3, ACCOUNT, LOC),
            MirStructFinish(4, 1, ACCOUNT, LOC),
        ))
        self.assertEqual(
            values[4],
            _StructValue("Account", (("id", 7), ("balance", 9))),
        )

    def test_checked_struct_field_projection_executes_directly(self):
        values = _run((
            MirStructNew(1, "Account", ("id", "balance"), ACCOUNT, LOC),
            MirConst(2, 7, INT, LOC),
            MirStructSet(1, "id", 2, ACCOUNT, LOC),
            MirConst(3, 9, INT, LOC),
            MirStructSet(1, "balance", 3, ACCOUNT, LOC),
            MirStructFinish(4, 1, ACCOUNT, LOC),
            MirMember(5, 4, "id", INT, LOC),
        ))
        self.assertEqual(values[5], 7)

    def test_missing_required_field_fails_at_finish(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "missing required struct fields: balance"):
            _run((
                MirStructNew(1, "Account", ("id", "balance"), ACCOUNT, LOC),
                MirConst(2, 7, INT, LOC),
                MirStructSet(1, "id", 2, ACCOUNT, LOC),
                MirStructFinish(3, 1, ACCOUNT, LOC),
            ))

    def test_extra_field_fails_at_set(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "struct field outside sealed contract"):
            _run((
                MirStructNew(1, "Account", ("id",), ACCOUNT, LOC),
                MirConst(2, 1, INT, LOC),
                MirStructSet(1, "admin", 2, ACCOUNT, LOC),
            ))

    def test_duplicate_assignment_fails_before_overwrite(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "duplicate struct field assignment"):
            _run((
                MirStructNew(1, "Account", ("id",), ACCOUNT, LOC),
                MirConst(2, 7, INT, LOC),
                MirStructSet(1, "id", 2, ACCOUNT, LOC),
                MirConst(3, 8, INT, LOC),
                MirStructSet(1, "id", 3, ACCOUNT, LOC),
            ))

    def test_finish_twice_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "struct builder already consumed"):
            _run((
                MirStructNew(1, "Account", ("id",), ACCOUNT, LOC),
                MirConst(2, 7, INT, LOC),
                MirStructSet(1, "id", 2, ACCOUNT, LOC),
                MirStructFinish(3, 1, ACCOUNT, LOC),
                MirStructFinish(4, 1, ACCOUNT, LOC),
            ))

    def test_set_after_finish_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "struct builder already consumed"):
            _run((
                MirStructNew(1, "Account", ("id",), ACCOUNT, LOC),
                MirConst(2, 7, INT, LOC),
                MirStructSet(1, "id", 2, ACCOUNT, LOC),
                MirStructFinish(3, 1, ACCOUNT, LOC),
                MirConst(4, 8, INT, LOC),
                MirStructSet(1, "id", 4, ACCOUNT, LOC),
            ))

    def test_duplicate_required_field_contract_fails_at_new(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "duplicate field in sealed struct contract"):
            _run((MirStructNew(1, "Account", ("id", "id"), ACCOUNT, LOC),))

    def test_invalid_builder_shape_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "invalid MIR struct builder"):
            _run((
                MirConst(1, 7, INT, LOC),
                MirStructFinish(2, 1, ACCOUNT, LOC),
            ))

    def test_finished_field_order_follows_sealed_contract(self):
        values = _run((
            MirStructNew(1, "Account", ("id", "balance"), ACCOUNT, LOC),
            MirConst(2, 9, INT, LOC),
            MirStructSet(1, "balance", 2, ACCOUNT, LOC),
            MirConst(3, 7, INT, LOC),
            MirStructSet(1, "id", 3, ACCOUNT, LOC),
            MirStructFinish(4, 1, ACCOUNT, LOC),
        ))
        self.assertEqual(values[4].fields, (("id", 7), ("balance", 9)))


if __name__ == "__main__":
    unittest.main()
