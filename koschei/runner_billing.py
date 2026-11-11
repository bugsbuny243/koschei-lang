"""Experimental deterministic usage metering; not a payment processor or runner."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

USD_PER_SECOND = Decimal("0.01")
BILLABLE_RESULTS = frozenset({"succeeded", "guest_failed", "guest_timeout"})


@dataclass(frozen=True)
class RunUsage:
    run_id: str
    tenant_id: str
    duration_ms: int
    result: str
    tariff_version: str = "pilot-v1"

    def __post_init__(self) -> None:
        if not self.run_id or not self.tenant_id or not self.tariff_version:
            raise ValueError("run, tenant and tariff identifiers are required")
        if type(self.duration_ms) is not int or self.duration_ms < 0:
            raise ValueError("duration_ms must be a nonnegative integer")
        if self.result not in BILLABLE_RESULTS | {"host_failed", "cancelled", "rejected"}:
            raise ValueError("unknown run result")


def invoice_total_usd(records: list[RunUsage], tenant_id: str) -> Decimal:
    """Aggregate billable milliseconds, round once at invoice level.

    Raises on duplicate ledger identities; never silently charges retries twice.
    A real service needs a durable atomic ledger and authorization before dispatch.
    """
    seen: set[tuple[str, str]] = set()
    milliseconds = 0
    for record in records:
        key = (record.run_id, record.tariff_version)
        if key in seen:
            raise ValueError("duplicate run/tariff ledger identity")
        seen.add(key)
        if record.tenant_id == tenant_id and record.result in BILLABLE_RESULTS:
            milliseconds += record.duration_ms
    return (Decimal(milliseconds) / Decimal(1000) * USD_PER_SECOND).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
