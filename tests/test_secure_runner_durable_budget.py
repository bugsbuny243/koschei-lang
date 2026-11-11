"""Durable prepaid pilot budget tests; no external payment processing."""
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from koschei.runner_durable_budget import DurablePilotBudget


class DurablePilotBudgetTests(unittest.TestCase):
    def test_reserve_settle_reopen_and_refund(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "budget.sqlite")
            budget = DurablePilotBudget(path)
            budget.seed_tenant("t", Decimal("5.00"))
            self.assertEqual(budget.reserve("t", "a", 60000), Decimal("0.60"))
            budget.close()
            budget = DurablePilotBudget(path)
            self.assertEqual(budget.available("t"), Decimal("4.40"))
            self.assertEqual(budget.settle("t", "a", 8000, True), Decimal("0.08"))
            self.assertEqual(budget.available("t"), Decimal("4.92"))
            budget.close()

    def test_failed_duplicate_reservation_rolls_back_debit(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = DurablePilotBudget(str(Path(tmp) / "b.sqlite"))
            budget.seed_tenant("t", Decimal("1.00"))
            budget.reserve("t", "a", 1000)
            with self.assertRaises(Exception):
                budget.reserve("t", "a", 1000)
            self.assertEqual(budget.available("t"), Decimal("0.99"))
            budget.close()

    def test_repeated_settlement_rejected_and_host_failure_refunded(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = DurablePilotBudget(str(Path(tmp) / "b.sqlite"))
            budget.seed_tenant("t", Decimal("1.00"))
            budget.reserve("t", "a", 10000)
            self.assertEqual(budget.settle("t", "a", 5000, False), Decimal("0.00"))
            self.assertEqual(budget.available("t"), Decimal("1.00"))
            with self.assertRaises(ValueError):
                budget.settle("t", "a", 5000, False)
            budget.close()

    def test_parallel_sqlite_connections_no_overspend(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "b.sqlite")
            budget = DurablePilotBudget(path)
            budget.seed_tenant("t", Decimal("0.10"))
            budget.close()
            barrier = threading.Barrier(4)
            outcomes = []
            lock = threading.Lock()

            def attempt(i):
                db = DurablePilotBudget(path)
                try:
                    barrier.wait()
                    try:
                        db.reserve("t", f"run-{i}", 6000)
                        result = True
                    except ValueError:
                        result = False
                    with lock:
                        outcomes.append(result)
                finally:
                    db.close()

            threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
            self.assertEqual(sum(outcomes), 1)
            budget = DurablePilotBudget(path)
            self.assertEqual(budget.available("t"), Decimal("0.04"))
            budget.close()


if __name__ == "__main__":
    unittest.main()
