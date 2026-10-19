"""Atomic pilot accounting tests; runner and payment integrations absent."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from koschei.runner_accounting import AtomicPilotAccounting
from koschei.runner_billing import RunUsage


class AtomicPilotAccountingTests(unittest.TestCase):
    def test_settle_records_usage_and_releases_unused_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AtomicPilotAccounting(str(Path(tmp) / "pilot.sqlite"))
            db.seed_tenant("t", Decimal("5.00"))
            db.reserve("t", "a", 60000)
            self.assertEqual(
                db.settle_run(RunUsage("a", "t", 8000, "succeeded")),
                Decimal("0.08"),
            )
            self.assertEqual(db.available("t"), Decimal("4.92"))
            row = db._db.execute(
                "SELECT duration_ms, result FROM runner_usage WHERE run_id='a'"
            ).fetchone()
            self.assertEqual(row, (8000, "succeeded"))
            db.close()

    def test_duplicate_usage_rolls_back_balance_and_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AtomicPilotAccounting(str(Path(tmp) / "pilot.sqlite"))
            db.seed_tenant("t", Decimal("1.00"))
            db.reserve("t", "a", 10000)
            db._db.execute(
                "INSERT INTO runner_usage VALUES ('t','a','pilot-v1',1,'succeeded')"
            )
            with self.assertRaises(Exception):
                db.settle_run(RunUsage("a", "t", 5000, "succeeded"))
            self.assertEqual(db.available("t"), Decimal("0.90"))
            row = db._db.execute(
                "SELECT state FROM pilot_hold WHERE run_id='a'"
            ).fetchone()
            self.assertEqual(row, ("active",))
            db.close()

    def test_host_failure_free_and_duplicate_settlement_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AtomicPilotAccounting(str(Path(tmp) / "pilot.sqlite"))
            db.seed_tenant("t", Decimal("1.00"))
            db.reserve("t", "a", 10000)
            self.assertEqual(
                db.settle_run(RunUsage("a", "t", 5000, "host_failed")),
                Decimal("0.00"),
            )
            self.assertEqual(db.available("t"), Decimal("1.00"))
            with self.assertRaises(ValueError):
                db.settle_run(RunUsage("a", "t", 5000, "host_failed"))
            db.close()


    def test_fractional_cent_reconciliation_detects_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AtomicPilotAccounting(str(Path(tmp) / "pilot.sqlite"))
            db.seed_tenant("t", Decimal("1.00"))
            for i in range(10):
                run_id = f"short-{i}"
                db.reserve("t", run_id, 100)
                db.settle_run(RunUsage(run_id, "t", 100, "succeeded"))
            self.assertEqual(db.invoiced_total_usd("t"), Decimal("0.01"))
            self.assertEqual(db.settled_total_usd("t"), Decimal("0.00"))
            self.assertNotEqual(db.invoiced_total_usd("t"), db.settled_total_usd("t"))
            db.close()

    def test_cross_tenant_settlement_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AtomicPilotAccounting(str(Path(tmp) / "pilot.sqlite"))
            db.seed_tenant("a", Decimal("1.00"))
            db.seed_tenant("b", Decimal("1.00"))
            db.reserve("a", "run-1", 1000)
            with self.assertRaises(ValueError):
                db.settle_run(RunUsage("run-1", "b", 1000, "succeeded"))
            self.assertEqual(db.available("a"), Decimal("0.99"))
            self.assertEqual(db.available("b"), Decimal("1.00"))
            db.close()


if __name__ == "__main__":
    unittest.main()
