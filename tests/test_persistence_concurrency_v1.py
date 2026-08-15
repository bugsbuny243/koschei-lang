from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import unittest

from koschei.interpreter import KsError, PersistCaps, SystemCaps


class PersistenceConcurrencyV1Tests(unittest.TestCase):
    def test_two_authorized_commits_leave_one_complete_object_not_a_torn_mix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("initial", encoding="utf-8")

            first = SystemCaps().persist.allow(str(target), 512 * 1024, 5000)
            second = SystemCaps().persist.allow(str(target), 512 * 1024, 5000)
            self.assertIsInstance(first, PersistCaps)
            self.assertIsInstance(second, PersistCaps)

            value_a = "A" * (128 * 1024)
            value_b = "B" * (128 * 1024)
            barrier = threading.Barrier(3)
            results: list[object] = []

            def writer(token: PersistCaps, value: str) -> None:
                barrier.wait()
                results.append(token.commit(value))

            left = threading.Thread(target=writer, args=(first, value_a))
            right = threading.Thread(target=writer, args=(second, value_b))
            left.start()
            right.start()
            barrier.wait()
            left.join(timeout=10)
            right.join(timeout=10)

            self.assertFalse(left.is_alive())
            self.assertFalse(right.is_alive())
            self.assertEqual(len(results), 2)
            for result in results:
                if isinstance(result, KsError):
                    self.fail(f"authorized concurrent commit failed unexpectedly: {result.message}")

            observed = target.read_text(encoding="utf-8")
            self.assertIn(observed, {value_a, value_b})
            self.assertEqual(len(observed), len(value_a))
            self.assertEqual(
                [
                    item.name
                    for item in target.parent.iterdir()
                    if item.name.startswith(".koschei-persist-")
                ],
                [],
            )

    def test_concurrency_contract_does_not_claim_compare_and_swap(self) -> None:
        # This test intentionally documents the v1 boundary: both writers are
        # authorized to replace the same exact object. Atomic visibility prevents
        # a torn file; it does not provide version checks or lost-update detection.
        self.assertFalse(hasattr(PersistCaps, "compare_and_swap"))
        self.assertFalse(hasattr(PersistCaps, "transaction"))


if __name__ == "__main__":
    unittest.main()
