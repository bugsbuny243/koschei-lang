from __future__ import annotations

from dataclasses import replace
import unittest

from koschei.native_external_boundary_v1 import NativeExternalBoundaryError
from koschei.native_nested_external_projection_v1 import (
    NativeNestedExternalProjectionError,
    NestedProjectionContractV1,
    NestedProjectionRuleV1,
    admit_nested_external_json_v1,
    seal_nested_projection_v1,
)
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE


KEY = b"k" * 32
PROJECT = b"p" * 16
BOUNDARY = b"b" * 16


def contract() -> NestedProjectionContractV1:
    return NestedProjectionContractV1(
        PROJECT,
        BOUNDARY,
        (
            NestedProjectionRuleV1(0, ("order", "amount"), WHOLE, max_abs_whole=1000),
            NestedProjectionRuleV1(1, ("order", "approved"), TRUTH),
            NestedProjectionRuleV1(2, ("profile", "display", "label"), GLYPHS, max_glyph_bytes=32),
        ),
        issued_epoch=10,
        expires_epoch=20,
        max_payload_bytes=4096,
    )


def payload():
    return {
        "order": {"amount": 40, "approved": True},
        "profile": {"display": {"label": "ok"}},
    }


class NativeNestedExternalProjectionV1Tests(unittest.TestCase):
    def test_exact_nested_shape_projects_anonymous_native_slots(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        admission = admit_nested_external_json_v1(sealed, KEY, current_epoch=12, payload=payload())
        self.assertEqual(admission.boundary_id, BOUNDARY)
        self.assertEqual(tuple(item.domain for item in admission.values), (WHOLE, TRUTH, GLYPHS))
        self.assertEqual(tuple(item.value for item in admission.values), (40, True, "ok"))

    def test_unknown_nested_sibling_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        data = payload()
        data["order"]["currency"] = "USD"
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "shape"):
            admit_nested_external_json_v1(sealed, KEY, current_epoch=12, payload=data)

    def test_unknown_top_level_sibling_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        data = payload()
        data["debug"] = True
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "shape"):
            admit_nested_external_json_v1(sealed, KEY, current_epoch=12, payload=data)

    def test_missing_nested_leaf_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        data = payload()
        del data["profile"]["display"]["label"]
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "shape"):
            admit_nested_external_json_v1(sealed, KEY, current_epoch=12, payload=data)

    def test_branch_instead_of_leaf_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        data = payload()
        data["order"]["amount"] = {"value": 40}
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "leaf"):
            admit_nested_external_json_v1(sealed, KEY, current_epoch=12, payload=data)

    def test_scalar_coercion_is_rejected_after_projection(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        data = payload()
        data["order"]["amount"] = "40"
        with self.assertRaisesRegex(NativeExternalBoundaryError, "without coercion"):
            admit_nested_external_json_v1(sealed, KEY, current_epoch=12, payload=data)

    def test_sealed_contract_tamper_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        tampered = replace(sealed, canonical_contract=sealed.canonical_contract.replace(b'"amount"', b'"totalx"'))
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "authentication"):
            admit_nested_external_json_v1(tampered, KEY, current_epoch=12, payload=payload())

    def test_wrong_key_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "authentication"):
            admit_nested_external_json_v1(sealed, b"z" * 32, current_epoch=12, payload=payload())

    def test_leaf_branch_prefix_collision_is_rejected_at_seal_time(self):
        bad = replace(
            contract(),
            rules=(
                NestedProjectionRuleV1(0, ("profile",), GLYPHS),
                NestedProjectionRuleV1(1, ("profile", "name"), GLYPHS),
            ),
        )
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "leaf and branch"):
            seal_nested_projection_v1(bad, KEY)

    def test_stale_epoch_is_rejected(self):
        sealed = seal_nested_projection_v1(contract(), KEY)
        with self.assertRaisesRegex(NativeNestedExternalProjectionError, "stale"):
            admit_nested_external_json_v1(sealed, KEY, current_epoch=21, payload=payload())


if __name__ == "__main__":
    unittest.main()
