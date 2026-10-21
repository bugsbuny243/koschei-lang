"""Experimental SQLite usage ledger with atomic run identity and invoice arithmetic.

Not a payment processor. Does not reserve funds or launch guest programs.
"""
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

from koschei.runner_billing import BILLABLE_RESULTS, RunUsage, USD_PER_SECOND


class UsageLedger:
    def __init__(self, database_path: str):
        self._db = sqlite3.connect(database_path, timeout=10, isolation_level=None)
        self._db.execute("PRAGMA busy_timeout = 10000")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS runner_usage (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                tariff_version TEXT NOT NULL,
                duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
                result TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id, tariff_version)
            )
        """)
        # A run identity must not be reused for a different tenant.
        self._db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS runner_usage_global_identity
            ON runner_usage (run_id, tariff_version)
        """)

    def close(self) -> None:
        self._db.close()

    def record(self, usage: RunUsage) -> None:
        # SQLite's unique constraint is the concurrency/idempotency boundary.
        try:
            self._db.execute(
                "INSERT INTO runner_usage "
                "(tenant_id, run_id, tariff_version, duration_ms, result) "
                "VALUES (?, ?, ?, ?, ?)",
                (usage.tenant_id, usage.run_id, usage.tariff_version,
                 usage.duration_ms, usage.result),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("duplicate run/tariff ledger identity") from exc

    def total_usd(self, tenant_id: str, tariff_version: str = "pilot-v1") -> Decimal:
        if not tenant_id or not tariff_version:
            raise ValueError("tenant and tariff required")
        # Read and sum integer milliseconds in Python to avoid SQLite SUM
        # integer overflow on very large ledgers.
        rows = self._db.execute(
            "SELECT duration_ms, result FROM runner_usage "
            "WHERE tenant_id = ? AND tariff_version = ?",
            (tenant_id, tariff_version),
        )
        total_ms = sum(ms for ms, result in rows if result in BILLABLE_RESULTS)
        return (Decimal(total_ms) / Decimal(1000) * USD_PER_SECOND).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
