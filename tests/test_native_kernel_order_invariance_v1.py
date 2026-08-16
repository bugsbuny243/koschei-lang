from __future__ import annotations

import itertools
import unittest

from koschei.native_kernel_v1 import check_native_kernel


class NativeKernelOrderInvarianceV1Tests(unittest.TestCase):
    def test_all_witness_clause_permutations_produce_same_dependency_reality(self) -> None:
        clauses = (
            "witness base 40",
            "witness fee 2",
            "witness total sum base fee",
            "witness doubled product total 2",
        )
        expected_order = ("base", "fee", "total", "doubled")
        for permutation in itertools.permutations(clauses):
            # resolve may appear between witness clauses; source position is not
            # control flow. Put it in the middle for every permutation.
            lines = list(permutation)
            lines.insert(2, "resolve doubled")
            checked = check_native_kernel("\n".join(lines) + "\n")
            self.assertEqual(checked.value, 84)
            self.assertEqual(checked.dependency_order, expected_order)


if __name__ == "__main__":
    unittest.main()
