"""Persistent metering contract tests. No payment processing."""
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from koschei.runner_billing import RunUsage
from koschei.runner_ledger import UsageLedger


class UsageLedgerTests(unittest.TestCase):
    def test_persists_after_reopen_and_rounds_invoice_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "usage.sqlite")
            ledger = UsageLedger(path)
            ledger.record(RunUsage("a", "t", 250, "succeeded"))
            ledger.record(RunUsage("b", "t", 750, "succeeded"))
            ledger.close()
            ledger = UsageLedger(path)
            self.assertEqual(ledger.total_usd("t"), Decimal("0.01"))
            ledger.close()

    def test_platform_fault_not_billable_and_tenants_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = UsageLedger(str(Path(tmp) / "usage.sqlite"))
            ledger.record(RunUsage("a", "t", 1000, "succeeded"))
            ledger.record(RunUsage("b", "t", 100000, "host_failed"))
            ledger.record(RunUsage("c", "other", 60000, "succeeded"))
            self.assertEqual(ledger.total_usd("t"), Decimal("0.01"))
            self.assertEqual(ledger.total_usd("other"), Decimal("0.60"))
            ledger.close()

    def test_duplicate_identity_rejected_across_tenants(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = UsageLedger(str(Path(tmp) / "usage.sqlite"))
            ledger.record(RunUsage("same", "t", 1000, "succeeded"))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                ledger.record(RunUsage("same", "other", 1000, "succeeded"))
            ledger.close()

    def test_parallel_connections_only_one_insert_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "usage.sqlite")
            UsageLedger(path).close()
            barrier = threading.Barrier(4)
            results = []
            lock = threading.Lock()

            def attempt():
                ledger = UsageLedger(path)
                try:
                    barrier.wait()
                    try:
                        ledger.record(RunUsage("same", "t", 1000, "succeeded"))
                        success = True
                    except ValueError:
                        success = False
                    with lock:
                        results.append(success)
                finally:
                    ledger.close()

            threads = [threading.Thread(target=attempt) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
            self.assertEqual(sum(results), 1)
            ledger = UsageLedger(path)
            self.assertEqual(ledger.total_usd("t"), Decimal("0.01"))
            ledger.close()


if __name__ == "__main__":
    unittest.main()
