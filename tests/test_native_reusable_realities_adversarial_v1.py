from __future__ import annotations

import unittest

from koschei.native_reusable_realities_v1 import (
    NativeReusableRealizationSpecV1,
    NativeReusableRealityError,
    encode_native_reusable_graph_secret,
)


class NativeReusableRealitiesAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_id = bytes.fromhex("c1" * 16)
        self.root_id = bytes.fromhex("c2" * 16)
        self.reusable_id = bytes.fromhex("c3" * 16)
        self.other_id = bytes.fromhex("c4" * 16)
        self.root = (
            b"witness value conduit 0\n"
            b"resolve value\n"
        )
        self.template = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )

    def spec(self, **changes):
        values = dict(
            realization_id=bytes.fromhex("d1" * 16),
            root_slot=0,
            reusable_object_id=self.reusable_id,
            inputs=(40, 2),
            issued_epoch=1,
            expires_epoch=2,
        )
        values.update(changes)
        return NativeReusableRealizationSpecV1(**values)

    def encode(self, *, objects=None, realizations=None):
        return encode_native_reusable_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=objects or {self.root_id: self.root, self.reusable_id: self.template},
            current_epoch=1,
            realizations=realizations or (self.spec(),),
        )

    def test_input_vector_must_exactly_match_reusable_conduit_contract(self) -> None:
        for inputs in ((40,), (40, 2, 1)):
            with self.subTest(inputs=inputs):
                with self.assertRaisesRegex(NativeReusableRealityError, "input vector length"):
                    self.encode(realizations=(self.spec(inputs=inputs),))

    def test_duplicate_realization_identity_or_root_slot_fails_closed(self) -> None:
        first = self.spec()
        with self.assertRaises(NativeReusableRealityError):
            self.encode(realizations=(first, self.spec(root_slot=1)))
        with self.assertRaises(NativeReusableRealityError):
            self.encode(
                realizations=(
                    first,
                    self.spec(realization_id=bytes.fromhex("d2" * 16), root_slot=0),
                )
            )

    def test_authority_effect_input_and_output_inflation_fail_closed(self) -> None:
        attacks = (
            self.spec(authority_ceiling=1),
            self.spec(effect_ceiling=1),
            self.spec(inputs=(41, 2), max_abs_input=40),
            self.spec(max_abs_output=41),
        )
        for spec in attacks:
            with self.subTest(spec=spec):
                with self.assertRaises(NativeReusableRealityError):
                    self.encode(realizations=(spec,))

    def test_orphan_reusable_object_is_rejected(self) -> None:
        objects = {
            self.root_id: self.root,
            self.reusable_id: self.template,
            self.other_id: self.template,
        }
        with self.assertRaisesRegex(NativeReusableRealityError, "orphan reusable object"):
            self.encode(objects=objects, realizations=(self.spec(),))

    def test_reusable_conduits_must_be_contiguous_from_zero(self) -> None:
        malformed = (
            b"witness left conduit 0\n"
            b"witness right conduit 2\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )
        with self.assertRaisesRegex(NativeReusableRealityError, "contiguous"):
            self.encode(objects={self.root_id: self.root, self.reusable_id: malformed})

    def test_same_reusable_object_is_allowed_to_back_multiple_distinct_realizations(self) -> None:
        root = (
            b"witness a conduit 0\n"
            b"witness b conduit 1\n"
            b"witness total sum a b\n"
            b"resolve total\n"
        )
        payload = self.encode(
            objects={self.root_id: root, self.reusable_id: self.template},
            realizations=(
                self.spec(),
                self.spec(
                    realization_id=bytes.fromhex("d2" * 16),
                    root_slot=1,
                    inputs=(10, 5),
                ),
            ),
        )
        self.assertGreater(len(payload), 0)


if __name__ == "__main__":
    unittest.main()
