from __future__ import annotations

from dataclasses import replace
import unittest

from koschei.native_sealed_collection_reality_v1 import (
    NativeSealedCollectionError,
    SealedCollectionContractV1,
    admit_collection_reality_v1,
    project_collection_all_v1,
    project_collection_any_v1,
    project_collection_count_v1,
    project_collection_merge_v1,
    project_collection_sum_v1,
    seal_collection_contract_v1,
)
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE


KEY = b"k" * 32
PROJECT = b"p" * 16
COLLECTION = b"c" * 16


def whole_contract() -> SealedCollectionContractV1:
    return SealedCollectionContractV1(
        PROJECT,
        COLLECTION,
        WHOLE,
        1,
        4,
        10,
        20,
        max_abs_whole=100,
        max_total_bytes=64,
    )


class NativeSealedCollectionRealityV1Tests(unittest.TestCase):
    def test_whole_collection_is_bounded_and_projects_without_indexing(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        reality = admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=(10, 20, 30))
        self.assertEqual(reality.domain, WHOLE)
        self.assertEqual(reality.count, 3)
        self.assertEqual(len(reality.digest), 32)
        self.assertEqual(project_collection_count_v1(reality).value.value, 3)
        self.assertEqual(project_collection_sum_v1(reality).value.value, 60)

    def test_cardinality_ceiling_is_fail_closed(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "cardinality"):
            admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=(1, 2, 3, 4, 5))

    def test_scalar_coercion_is_rejected(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "without coercion"):
            admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=(1, "2"))

    def test_whole_item_ceiling_is_enforced(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "absolute-value"):
            admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=(101,))

    def test_truth_collection_supports_closed_any_all_projections(self):
        contract = replace(whole_contract(), domain=TRUTH, min_count=2, max_count=3)
        sealed = seal_collection_contract_v1(contract, KEY)
        reality = admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=(True, False, True))
        self.assertFalse(project_collection_all_v1(reality).value.value)
        self.assertTrue(project_collection_any_v1(reality).value.value)

    def test_glyph_collection_supports_closed_merge_projection(self):
        contract = replace(
            whole_contract(),
            domain=GLYPHS,
            min_count=2,
            max_count=3,
            max_glyph_bytes=8,
            max_total_bytes=32,
        )
        sealed = seal_collection_contract_v1(contract, KEY)
        reality = admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=("ko", "schei"))
        result = project_collection_merge_v1(reality)
        self.assertEqual(result.value.domain, GLYPHS)
        self.assertEqual(result.value.value, "koschei")

    def test_wrong_projection_domain_is_rejected(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        reality = admit_collection_reality_v1(sealed, KEY, current_epoch=12, items=(1, 2))
        with self.assertRaisesRegex(NativeSealedCollectionError, "truth collection"):
            project_collection_any_v1(reality)

    def test_descriptor_tamper_is_rejected(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        tampered = replace(sealed, canonical_contract=sealed.canonical_contract.replace(b'"max":4', b'"max":9'))
        with self.assertRaisesRegex(NativeSealedCollectionError, "authentication"):
            admit_collection_reality_v1(tampered, KEY, current_epoch=12, items=(1,))

    def test_wrong_key_is_rejected(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "authentication"):
            admit_collection_reality_v1(sealed, b"z" * 32, current_epoch=12, items=(1,))

    def test_stale_contract_is_rejected(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "stale"):
            admit_collection_reality_v1(sealed, KEY, current_epoch=21, items=(1,))

    def test_ambient_mapping_and_text_are_not_collection_streams(self):
        sealed = seal_collection_contract_v1(whole_contract(), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "ambient"):
            admit_collection_reality_v1(sealed, KEY, current_epoch=12, items={"0": 1})
        with self.assertRaisesRegex(NativeSealedCollectionError, "ambient"):
            admit_collection_reality_v1(sealed, KEY, current_epoch=12, items="123")

    def test_authority_and_effects_cannot_be_smuggled_into_contract(self):
        with self.assertRaisesRegex(NativeSealedCollectionError, "zero authority"):
            seal_collection_contract_v1(replace(whole_contract(), authority_ceiling=1), KEY)
        with self.assertRaisesRegex(NativeSealedCollectionError, "zero authority"):
            seal_collection_contract_v1(replace(whole_contract(), effect_ceiling=1), KEY)


if __name__ == "__main__":
    unittest.main()
