from __future__ import annotations

import unittest

from koschei.native_reality_mesh_v1 import (
    MeshValue,
    NativeRealityMeshError,
    evaluate_native_reality_mesh_v1,
)
from koschei.native_value_domains_v1 import NativeValue, TRUTH, WHOLE


class NativeRealityMeshV1Tests(unittest.TestCase):
    def test_order_free_mesh_has_same_digest(self) -> None:
        left = evaluate_native_reality_mesh_v1(
            "witness a 7\n"
            "witness b 9\n"
            "witness group mesh 2 a b\n"
            "resolve group\n"
        )
        right = evaluate_native_reality_mesh_v1(
            "witness a 7\n"
            "witness b 9\n"
            "witness group mesh 2 b a\n"
            "resolve group\n"
        )
        self.assertIsInstance(left, MeshValue)
        self.assertIsInstance(right, MeshValue)
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(left.members, right.members)

    def test_span_and_contains_are_native_value_results(self) -> None:
        size = evaluate_native_reality_mesh_v1(
            "witness a 7\n"
            "witness b 9\n"
            "witness group mesh 2 a b\n"
            "witness size span group\n"
            "resolve size\n"
        )
        self.assertEqual(size, NativeValue(WHOLE, 2))
        contains = evaluate_native_reality_mesh_v1(
            "witness a 7\n"
            "witness b 9\n"
            "witness group mesh 2 a b\n"
            "witness found contains group b\n"
            "resolve found\n"
        )
        self.assertEqual(contains, NativeValue(TRUTH, True))

    def test_duplicate_values_fail_closed(self) -> None:
        with self.assertRaises(NativeRealityMeshError):
            evaluate_native_reality_mesh_v1(
                "witness a 7\n"
                "witness b 7\n"
                "witness group mesh 2 a b\n"
                "resolve group\n"
            )

    def test_cross_domain_members_fail_closed(self) -> None:
        with self.assertRaises(NativeRealityMeshError):
            evaluate_native_reality_mesh_v1(
                "witness a 7\n"
                "witness b truth yes\n"
                "witness group mesh 2 a b\n"
                "resolve group\n"
            )

    def test_mesh_is_not_legacy_collection_syntax(self) -> None:
        for source in (
            "witness group [7,9]\nresolve group\n",
            "witness group list 2 7 9\nresolve group\n",
            "witness group map 1 a 7\nresolve group\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(Exception):
                    evaluate_native_reality_mesh_v1(source)


if __name__ == "__main__":
    unittest.main()
