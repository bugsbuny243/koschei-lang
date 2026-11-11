"""Experimental atomic SQLite settlement of prepaid hold and usage record.

Not a payment service. Requires a trusted runner to supply elapsed milliseconds
and classification. One local SQLite database only.
"""
from decimal import Decimal, ROUND_HALF_UP

from koschei.runner_billing import BILLABLE_RESULTS, RunUsage, USD_PER_SECOND
from koschei.runner_durable_budget import DurablePilotBudget


class AtomicPilotAccounting(DurablePilotBudget):
    def __init__(self, path: str):
        super().__init__(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS runner_usage ("
            "tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, "
            "tariff_version TEXT NOT NULL, duration_ms INTEGER NOT NULL "
            "CHECK(duration_ms >= 0), result TEXT NOT NULL, "
            "PRIMARY KEY (run_id, tariff_version))"
        )

    def invoiced_total_usd(self, tenant_id: str, tariff_version: str = "pilot-v1") -> Decimal:
        """Independent aggregate-time invoice estimate, not a payment charge."""
        if not tenant_id or not tariff_version:
            raise ValueError("tenant and tariff required")
        rows = self._db.execute(
            "SELECT duration_ms, result FROM runner_usage "
            "WHERE tenant_id=? AND tariff_version=?",
            (tenant_id, tariff_version),
        )
        total_ms = sum(ms for ms, result in rows if result in BILLABLE_RESULTS)
        return (Decimal(total_ms) / 1000 * USD_PER_SECOND).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def settled_total_usd(self, tenant_id: str) -> Decimal:
        """Amount actually deducted from prepaid balance, in whole cents."""
        if not tenant_id:
            raise ValueError("tenant required")
        row = self._db.execute(
            "SELECT COALESCE(SUM(charged_cents), 0) FROM pilot_hold "
            "WHERE tenant_id=? AND state='settled'", (tenant_id,),
        ).fetchone()
        return Decimal(row[0]) / 100

    def settle_run(self, usage: RunUsage) -> Decimal:
        """Commit balance release and usage insert together or roll both back."""
        if usage.tariff_version != "pilot-v1":
            raise ValueError("unsupported prepaid tariff version")
        if usage.result not in BILLABLE_RESULTS | {"host_failed", "cancelled", "rejected"}:
            raise ValueError("invalid outcome")
        with self._transaction():
            row = self._db.execute(
                "SELECT reserved_cents, max_duration_ms FROM pilot_hold "
                "WHERE tenant_id=? AND run_id=? AND state='active'",
                (usage.tenant_id, usage.run_id),
            ).fetchone()
            if row is None:
                raise ValueError("missing or already settled reservation")
            reserved, maximum = row
            if usage.duration_ms > maximum:
                raise ValueError("execution exceeded authorized maximum")
            billable = usage.result in BILLABLE_RESULTS
            # Charge only the increase in the aggregate rounded invoice.
            # SQLite serializes this read/modify/write via BEGIN IMMEDIATE.
            prior_ms = sum(
                ms for ms, result in self._db.execute(
                    "SELECT duration_ms, result FROM runner_usage "
                    "WHERE tenant_id=? AND tariff_version=?",
                    (usage.tenant_id, usage.tariff_version),
                ) if result in BILLABLE_RESULTS
            )
            current_ms = prior_ms + (usage.duration_ms if billable else 0)
            prior_cents = int(
                (Decimal(prior_ms) / 1000 * USD_PER_SECOND * 100)
                .to_integral_value(rounding=ROUND_HALF_UP)
            )
            total_cents = int(
                (Decimal(current_ms) / 1000 * USD_PER_SECOND * 100)
                .to_integral_value(rounding=ROUND_HALF_UP)
            )
            cents = total_cents - prior_cents
            if cents > reserved:
                raise ValueError("charge exceeds reservation")
            self._db.execute(
                "INSERT INTO runner_usage "
                "(tenant_id, run_id, tariff_version, duration_ms, result) "
                "VALUES (?, ?, ?, ?, ?)",
                (usage.tenant_id, usage.run_id, usage.tariff_version,
                 usage.duration_ms, usage.result),
            )
            self._db.execute(
                "UPDATE pilot_hold SET state='settled', charged_cents=? "
                "WHERE tenant_id=? AND run_id=? AND state='active'",
                (cents, usage.tenant_id, usage.run_id),
            )
            self._db.execute(
                "UPDATE pilot_balance SET available_cents=available_cents+? "
                "WHERE tenant_id=?", (reserved - cents, usage.tenant_id),
            )
        return Decimal(cents) / 100
