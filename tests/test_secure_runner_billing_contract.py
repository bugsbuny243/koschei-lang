"""Contract tests for experimental invoice arithmetic; no real charges."""
import unittest
from decimal import Decimal

from koschei.runner_billing import RunUsage, invoice_total_usd


class RunnerBillingTests(unittest.TestCase):
    def test_aggregate_before_rounding(self):
        records = [RunUsage("a", "tenant-a", 250, "succeeded"),
                   RunUsage("b", "tenant-a", 750, "succeeded")]
        self.assertEqual(invoice_total_usd(records, "tenant-a"), Decimal("0.01"))

    def test_one_minute(self):
        self.assertEqual(invoice_total_usd(
            [RunUsage("a", "t", 60000, "succeeded")], "t"), Decimal("0.60"))

    def test_guest_errors_bill_host_errors_do_not(self):
        records = [RunUsage("a", "t", 1000, "guest_failed"),
                   RunUsage("b", "t", 1000, "guest_timeout"),
                   RunUsage("c", "t", 900000, "host_failed"),
                   RunUsage("d", "t", 900000, "cancelled"),
                   RunUsage("e", "t", 900000, "rejected")]
        self.assertEqual(invoice_total_usd(records, "t"), Decimal("0.02"))

    def test_tenant_separation(self):
        records = [RunUsage("a", "t", 1000, "succeeded"),
                   RunUsage("b", "other", 500000, "succeeded")]
        self.assertEqual(invoice_total_usd(records, "t"), Decimal("0.01"))

    def test_duplicate_identity_rejected(self):
        run = RunUsage("a", "t", 1000, "succeeded")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            invoice_total_usd([run, run], "t")

    def test_invalid_meter_rejected(self):
        for duration in (-1, 1.5, True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                RunUsage("a", "t", duration, "succeeded")

    def test_round_only_final_invoice(self):
        records = [RunUsage(str(i), "t", 100, "succeeded") for i in range(10)]
        self.assertEqual(invoice_total_usd(records, "t"), Decimal("0.01"))


if __name__ == "__main__":
    unittest.main()
