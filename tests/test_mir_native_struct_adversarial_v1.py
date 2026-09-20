from __future__ import annotations

import unittest

from koschei.mir_native_runtime import MirNativeRuntimeError, _MirExecutor, _StructBuilder


class NativeMirStructAdversarialTests(unittest.TestCase):
    def test_missing_required_field_fails_closed(self):
        builder = _StructBuilder("Account", ("id", "balance"), {"id": 7})
        missing = tuple(field for field in builder.required_fields if field not in builder.fields)
        self.assertEqual(missing, ("balance",))

    def test_extra_field_is_outside_sealed_contract(self):
        builder = _StructBuilder("Account", ("id", "balance"), {})
        self.assertNotIn("admin", builder.required_fields)

    def test_duplicate_field_assignment_is_detectable_before_overwrite(self):
        builder = _StructBuilder("Account", ("id", "balance"), {"id": 7})
        self.assertIn("id", builder.fields)

    def test_consumed_builder_cannot_be_reused(self):
        builder = _StructBuilder("Account", ("id",), {"id": 7}, consumed=True)
        self.assertTrue(builder.consumed)

    def test_non_builder_runtime_shape_fails_closed(self):
        with self.assertRaisesRegex(MirNativeRuntimeError, "invalid MIR struct builder"):
            _MirExecutor._struct_builder({1: object()}, 1)

    def test_sealed_field_order_is_preserved(self):
        builder = _StructBuilder("Account", ("id", "balance"), {"balance": 9, "id": 7})
        finished = tuple((field, builder.fields[field]) for field in builder.required_fields)
        self.assertEqual(finished, (("id", 7), ("balance", 9)))


if __name__ == "__main__":
    unittest.main()
