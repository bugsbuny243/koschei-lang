"""Tests for experimental in-memory budget; not a distributed ledger."""
import threading
import unittest
from decimal import Decimal

from koschei.runner_budget import PilotBudget


class PilotBudgetTests(unittest.TestCase):
    def test_reserve_and_refund_unused_time(self):
        budget = PilotBudget({"t": Decimal("5.00")})
        hold = budget.reserve("t", "run-1", 60000)
        self.assertEqual(hold.reserved_usd, Decimal("0.60"))
        self.assertEqual(budget.available("t"), Decimal("4.40"))
        self.assertEqual(budget.settle("t", "run-1", 8000, True), Decimal("0.08"))
        self.assertEqual(budget.available("t"), Decimal("4.92"))

    def test_insufficient_balance_rejected(self):
        budget = PilotBudget({"t": Decimal("0.05")})
        with self.assertRaisesRegex(ValueError, "insufficient"):
            budget.reserve("t", "run-1", 6000)
        self.assertEqual(budget.available("t"), Decimal("0.05"))

    def test_platform_failure_refunds(self):
        budget = PilotBudget({"t": Decimal("1.00")})
        budget.reserve("t", "run-1", 10000)
        self.assertEqual(budget.settle("t", "run-1", 4000, False), Decimal("0.00"))
        self.assertEqual(budget.available("t"), Decimal("1.00"))

    def test_duplicate_settlement_rejected(self):
        budget = PilotBudget({"t": Decimal("1.00")})
        budget.reserve("t", "run-1", 1000)
        budget.settle("t", "run-1", 1000, True)
        with self.assertRaises(ValueError):
            budget.settle("t", "run-1", 1000, True)
        with self.assertRaises(ValueError):
            budget.reserve("t", "run-1", 1000)

    def test_excess_runtime_cannot_be_settled(self):
        budget = PilotBudget({"t": Decimal("1.00")})
        budget.reserve("t", "run-1", 1000)
        with self.assertRaisesRegex(ValueError, "exceeded"):
            budget.settle("t", "run-1", 1001, True)
        self.assertEqual(budget.available("t"), Decimal("0.99"))

    def test_parallel_reservations_cannot_overspend(self):
        budget = PilotBudget({"t": Decimal("0.10")})
        results = []
        barrier = threading.Barrier(4)
        lock = threading.Lock()

        def attempt(i):
            barrier.wait()
            try:
                budget.reserve("t", str(i), 6000)
                outcome = True
            except ValueError:
                outcome = False
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(results), 1)
        self.assertEqual(budget.available("t"), Decimal("0.04"))

    def test_invalid_balance_rejected(self):
        for balance in (Decimal("-1"), Decimal("NaN"), Decimal("0.001")):
            with self.subTest(balance=str(balance)), self.assertRaises(ValueError):
                PilotBudget({"t": balance})


if __name__ == "__main__":
    unittest.main()
