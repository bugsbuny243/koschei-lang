"""Experimental durable prepaid budget ledger for one SQLite database.

No payment processing, no guest execution, no cross-database transaction.
"""
import sqlite3
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from koschei.runner_billing import USD_PER_SECOND


def _to_cents(amount: Decimal) -> int:
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
        raise ValueError("balance must be a finite nonnegative Decimal")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError("balance must have cent precision")
    return int(cents)


class DurablePilotBudget:
    """Atomic reserve/settle on SQLite. No distributed payment guarantee."""

    def __init__(self, path: str):
        self._db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self._db.execute("PRAGMA busy_timeout = 10000")
        self._db.execute("CREATE TABLE IF NOT EXISTS pilot_balance ("
                         "tenant_id TEXT PRIMARY KEY, available_cents INTEGER NOT NULL "
                         "CHECK(available_cents >= 0))")
        self._db.execute("CREATE TABLE IF NOT EXISTS pilot_hold ("
                         "run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                         "reserved_cents INTEGER NOT NULL, max_duration_ms INTEGER NOT NULL, "
                         "state TEXT NOT NULL CHECK(state IN ('active', 'settled')), "
                         "charged_cents INTEGER)")

    def close(self) -> None:
        self._db.close()

    def seed_tenant(self, tenant_id: str, amount: Decimal) -> None:
        if not tenant_id:
            raise ValueError("tenant required")
        cents = _to_cents(amount)
        with self._db:
            self._db.execute(
                "INSERT INTO pilot_balance (tenant_id, available_cents) VALUES (?, ?)",
                (tenant_id, cents),
            )

    def available(self, tenant_id: str) -> Decimal:
        row = self._db.execute("SELECT available_cents FROM pilot_balance "
                               "WHERE tenant_id=?", (tenant_id,)).fetchone()
        if row is None:
            raise ValueError("unknown tenant")
        return Decimal(row[0]) / 100

    def reserve(self, tenant_id: str, run_id: str, max_duration_ms: int) -> Decimal:
        if not tenant_id or not run_id or type(max_duration_ms) is not int or max_duration_ms <= 0:
            raise ValueError("invalid reservation")
        cents = int((Decimal(max_duration_ms) / 1000).to_integral_value(
            rounding=ROUND_CEILING))
        with self._db:
            self._db.execute("UPDATE pilot_balance SET available_cents = available_cents - ? "
                             "WHERE tenant_id = ? AND available_cents >= ?",
                             (cents, tenant_id, cents))
            if self._db.execute("SELECT changes()").fetchone()[0] != 1:
                raise ValueError("insufficient budget or unknown tenant")
            self._db.execute(
                "INSERT INTO pilot_hold "
                "(run_id, tenant_id, reserved_cents, max_duration_ms, state) "
                "VALUES (?, ?, ?, ?, 'active')",
                (run_id, tenant_id, cents, max_duration_ms),
            )
        return Decimal(cents) / 100

    def settle(self, tenant_id: str, run_id: str, duration_ms: int, billable: bool) -> Decimal:
        if type(duration_ms) is not int or duration_ms < 0 or type(billable) is not bool:
            raise ValueError("invalid settlement")
        with self._db:
            row = self._db.execute(
                "SELECT reserved_cents, max_duration_ms FROM pilot_hold "
                "WHERE tenant_id=? AND run_id=? AND state='active'",
                (tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise ValueError("missing or already settled reservation")
            reserved, maximum = row
            if duration_ms > maximum:
                raise ValueError("execution exceeded authorized maximum")
            raw = Decimal(duration_ms) / 1000 * USD_PER_SECOND if billable else Decimal(0)
            cents = int((raw * 100).to_integral_value(rounding=ROUND_HALF_UP))
            if cents > reserved:
                raise ValueError("charge exceeds reservation")
            self._db.execute(
                "UPDATE pilot_hold SET state='settled', charged_cents=? "
                "WHERE tenant_id=? AND run_id=? AND state='active'",
                (cents, tenant_id, run_id),
            )
            self._db.execute(
                "UPDATE pilot_balance SET available_cents=available_cents+? "
                "WHERE tenant_id=?", (reserved - cents, tenant_id),
            )
        return Decimal(cents) / 100
