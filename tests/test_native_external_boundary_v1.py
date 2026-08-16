import unittest

from koschei.native_external_boundary_v1 import (
    EXTERNAL_DB,
    EXTERNAL_HTTP,
    EXTERNAL_JSON,
    ExternalBoundaryContractV1,
    ExternalFieldRuleV1,
    NativeExternalBoundaryError,
    SealedExternalBoundaryV1,
    admit_external_mapping_v1,
    contract_fingerprint_v1,
    seal_external_boundary_v1,
)
from koschei.native_mixed_reuse_v1 import _materialize_typed
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE


KEY = b"k" * 32
PROJECT = b"p" * 16
BOUNDARY = b"b" * 16


def contract(kind=EXTERNAL_JSON, *, whole=100, glyphs=32, issued=7, expires=9):
    return ExternalBoundaryContractV1(
        PROJECT,
        BOUNDARY,
        kind,
        (
            ExternalFieldRuleV1(0, "amount", WHOLE, max_abs_whole=whole),
            ExternalFieldRuleV1(1, "approved", TRUTH),
            ExternalFieldRuleV1(2, "display.label", GLYPHS, max_glyph_bytes=glyphs),
        ),
        issued,
        expires,
        max_payload_bytes=256,
    )


class NativeExternalBoundaryV1Tests(unittest.TestCase):
    def test_json_mapping_admits_anonymous_typed_native_slots(self):
        sealed = seal_external_boundary_v1(contract(), KEY)
        admission = admit_external_mapping_v1(
            sealed,
            KEY,
            current_epoch=8,
            source_kind=EXTERNAL_JSON,
            payload={"amount": 40, "approved": True, "display.label": "ok"},
        )
        self.assertEqual(admission.boundary_id, BOUNDARY)
        self.assertEqual(tuple(value.domain for value in admission.values), (WHOLE, TRUTH, GLYPHS))
        self.assertEqual(tuple(value.value for value in admission.values), (40, True, "ok"))
        self.assertFalse(hasattr(admission, "external_names"))

    def test_admitted_values_feed_reusable_without_external_names_in_source(self):
        sealed = seal_external_boundary_v1(contract(), KEY)
        admission = admit_external_mapping_v1(
            sealed,
            KEY,
            current_epoch=8,
            source_kind=EXTERNAL_JSON,
            payload={"amount": 40, "approved": True, "display.label": "ok"},
        )
        source = (
            "witness amount conduit 0\n"
            "witness approved conduit 1\n"
            "witness label conduit 2\n"
            "witness amountok same amount 40\n"
            "witness expected glyphs 2 ok\n"
            "witness labelok same label expected\n"
            "witness both same approved amountok\n"
            "witness result same both labelok\n"
            "resolve result\n"
        )
        self.assertNotIn("display.label", source)
        result = _materialize_typed(source, {slot: value for slot, value in enumerate(admission.values)})
        self.assertEqual(result.value.domain, TRUTH)
        self.assertIs(result.value.value, True)

    def test_http_and_db_are_separate_sealed_source_kinds(self):
        for kind in (EXTERNAL_HTTP, EXTERNAL_DB):
            sealed = seal_external_boundary_v1(contract(kind), KEY)
            admission = admit_external_mapping_v1(
                sealed,
                KEY,
                current_epoch=8,
                source_kind=kind,
                payload={"amount": 1, "approved": False, "display.label": "x"},
            )
            self.assertEqual(len(admission.values), 3)
        sealed = seal_external_boundary_v1(contract(EXTERNAL_HTTP), KEY)
        with self.assertRaises(NativeExternalBoundaryError):
            admit_external_mapping_v1(
                sealed,
                KEY,
                current_epoch=8,
                source_kind=EXTERNAL_DB,
                payload={"amount": 1, "approved": False, "display.label": "x"},
            )

    def test_payload_key_set_must_exactly_match_sealed_contract(self):
        sealed = seal_external_boundary_v1(contract(), KEY)
        for payload in (
            {"amount": 1, "approved": True},
            {"amount": 1, "approved": True, "display.label": "x", "admin": True},
        ):
            with self.assertRaises(NativeExternalBoundaryError):
                admit_external_mapping_v1(sealed, KEY, current_epoch=8, source_kind=EXTERNAL_JSON, payload=payload)

    def test_no_scalar_coercion_is_permitted(self):
        sealed = seal_external_boundary_v1(contract(), KEY)
        bad_payloads = (
            {"amount": "40", "approved": True, "display.label": "x"},
            {"amount": True, "approved": True, "display.label": "x"},
            {"amount": 40, "approved": 1, "display.label": "x"},
            {"amount": 40, "approved": True, "display.label": 9},
        )
        for payload in bad_payloads:
            with self.assertRaises(NativeExternalBoundaryError):
                admit_external_mapping_v1(sealed, KEY, current_epoch=8, source_kind=EXTERNAL_JSON, payload=payload)

    def test_value_budgets_and_canonical_text_fail_closed(self):
        sealed = seal_external_boundary_v1(contract(whole=40, glyphs=4), KEY)
        for payload in (
            {"amount": 41, "approved": True, "display.label": "x"},
            {"amount": 40, "approved": True, "display.label": "abcde"},
            {"amount": 40, "approved": True, "display.label": "e\u0301"},
            {"amount": 40, "approved": True, "display.label": "a\nb"},
        ):
            with self.assertRaises(NativeExternalBoundaryError):
                admit_external_mapping_v1(sealed, KEY, current_epoch=8, source_kind=EXTERNAL_JSON, payload=payload)

    def test_contract_tamper_and_wrong_key_fail_authentication(self):
        sealed = seal_external_boundary_v1(contract(), KEY)
        tampered = SealedExternalBoundaryV1(sealed.canonical_contract.replace(b'"amount"', b'"adminx"'), sealed.tag)
        with self.assertRaises(NativeExternalBoundaryError):
            admit_external_mapping_v1(
                tampered,
                KEY,
                current_epoch=8,
                source_kind=EXTERNAL_JSON,
                payload={"adminx": 1, "approved": True, "display.label": "x"},
            )
        with self.assertRaises(NativeExternalBoundaryError):
            admit_external_mapping_v1(
                sealed,
                b"z" * 32,
                current_epoch=8,
                source_kind=EXTERNAL_JSON,
                payload={"amount": 1, "approved": True, "display.label": "x"},
            )

    def test_epoch_window_is_enforced(self):
        sealed = seal_external_boundary_v1(contract(issued=7, expires=9), KEY)
        payload = {"amount": 1, "approved": True, "display.label": "x"}
        for epoch in (6, 10):
            with self.assertRaises(NativeExternalBoundaryError):
                admit_external_mapping_v1(sealed, KEY, current_epoch=epoch, source_kind=EXTERNAL_JSON, payload=payload)

    def test_contract_requires_contiguous_anonymous_slots_and_zero_authority(self):
        bad_slot = ExternalBoundaryContractV1(
            PROJECT,
            BOUNDARY,
            EXTERNAL_JSON,
            (ExternalFieldRuleV1(1, "amount", WHOLE),),
            1,
            2,
        )
        with self.assertRaises(NativeExternalBoundaryError):
            seal_external_boundary_v1(bad_slot, KEY)
        privileged = ExternalBoundaryContractV1(
            PROJECT,
            BOUNDARY,
            EXTERNAL_JSON,
            (ExternalFieldRuleV1(0, "amount", WHOLE),),
            1,
            2,
            authority_ceiling=1,
        )
        with self.assertRaises(NativeExternalBoundaryError):
            seal_external_boundary_v1(privileged, KEY)

    def test_fingerprint_exposes_contract_identity_without_key_or_external_values(self):
        sealed = seal_external_boundary_v1(contract(), KEY)
        fingerprint = contract_fingerprint_v1(sealed)
        self.assertEqual(len(fingerprint), 32)
        self.assertNotEqual(fingerprint, KEY)
        self.assertNotIn(KEY, sealed.canonical_contract)


if __name__ == "__main__":
    unittest.main()
