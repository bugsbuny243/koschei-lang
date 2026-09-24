from __future__ import annotations

import unittest

from koschei.ast_nodes import SourceLocation
from koschei.mir_extension_instructions_v4 import MirMapFinish, MirMapInsert, MirMapNew
from koschei.mir_ir import MirConst
from koschei.mir_native_runtime import MirNativeRuntimeError, _MapValue, _MirExecutor
from koschei.type_system import INT, STRING, generic


LOC = SourceLocation(1, 1)
MAP = generic("Map", STRING, INT)


def _executor():
    executor = object.__new__(_MirExecutor)
    # Map/const transitions do not consult graph/module state. This harness
    # intentionally exercises the real instruction implementation directly.
    return executor


def _run(instructions):
    executor = _executor()
    values = {}
    environment = {}
    mutable = set()
    for instruction in instructions:
        executor._execute_instruction(instruction, values, environment, mutable, "root")
    return values


class NativeMirMapAdversarialTests(unittest.TestCase):
    def test_exact_map_executes_through_real_instruction_path(self):
        values = _run((
            MirMapNew(1, MAP, LOC),
            MirConst(2, "a", STRING, LOC),
            MirConst(3, 1, INT, LOC),
            MirMapInsert(1, (2, 3), MAP, LOC),
            MirConst(4, "b", STRING, LOC),
            MirConst(5, 2, INT, LOC),
            MirMapInsert(1, (4, 5), MAP, LOC),
            MirMapFinish(6, 1, MAP, LOC),
        ))
        self.assertEqual(values[6], _MapValue((("a", 1), ("b", 2))))

    def test_duplicate_key_fails_before_overwrite(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "duplicate Map key insertion"):
            _run((
                MirMapNew(1, MAP, LOC),
                MirConst(2, "same", STRING, LOC),
                MirConst(3, 1, INT, LOC),
                MirMapInsert(1, (2, 3), MAP, LOC),
                MirConst(4, "same", STRING, LOC),
                MirConst(5, 2, INT, LOC),
                MirMapInsert(1, (4, 5), MAP, LOC),
            ))

    def test_non_string_key_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "Map key must be String"):
            _run((
                MirMapNew(1, MAP, LOC),
                MirConst(2, 7, INT, LOC),
                MirConst(3, 1, INT, LOC),
                MirMapInsert(1, (2, 3), MAP, LOC),
            ))

    def test_finish_twice_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "map builder already consumed"):
            _run((
                MirMapNew(1, MAP, LOC),
                MirMapFinish(2, 1, MAP, LOC),
                MirMapFinish(3, 1, MAP, LOC),
            ))

    def test_insert_after_finish_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "map builder already consumed"):
            _run((
                MirMapNew(1, MAP, LOC),
                MirMapFinish(2, 1, MAP, LOC),
                MirConst(3, "late", STRING, LOC),
                MirConst(4, 1, INT, LOC),
                MirMapInsert(1, (3, 4), MAP, LOC),
            ))

    def test_invalid_builder_shape_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "invalid MIR map builder"):
            _run((
                MirConst(1, 7, INT, LOC),
                MirMapFinish(2, 1, MAP, LOC),
            ))

    def test_finished_order_follows_insertion_order(self):
        values = _run((
            MirMapNew(1, MAP, LOC),
            MirConst(2, "second", STRING, LOC),
            MirConst(3, 2, INT, LOC),
            MirMapInsert(1, (2, 3), MAP, LOC),
            MirConst(4, "first", STRING, LOC),
            MirConst(5, 1, INT, LOC),
            MirMapInsert(1, (4, 5), MAP, LOC),
            MirMapFinish(6, 1, MAP, LOC),
        ))
        self.assertEqual(
            values[6].entries,
            (("second", 2), ("first", 1)),
        )


if __name__ == "__main__":
    unittest.main()
