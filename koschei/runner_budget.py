"""Experimental single-process budget reservation prototype.

NOT durable, distributed, a payment processor, or safe for multi-worker production.
"""
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from koschei.runner_billing import USD_PER_SECOND


def _cents(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("balance must be a finite nonnegative Decimal")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("balance must have cent precision")
    return value


@dataclass(frozen=True)
class Reservation:
    tenant_id: str
    run_id: str
    reserved_usd: Decimal
    max_duration_ms: int


class PilotBudget:
    """Thread-safe in-memory proof of atomic reservations for one process."""

    def __init__(self, balances: dict[str, Decimal]):
        self._lock = Lock()
        self._available = {tenant: _cents(balance) for tenant, balance in balances.items()}
        self._active: dict[tuple[str, str], Reservation] = {}
        self._finished: set[tuple[str, str]] = set()

    def reserve(self, tenant_id: str, run_id: str, max_duration_ms: int) -> Reservation:
        if not tenant_id or not run_id or type(max_duration_ms) is not int or max_duration_ms <= 0:
            raise ValueError("invalid reservation")
        # Ceiling of worst-case milliseconds to cents, so an authorized run
        # can never cost more than its reserve at the advertised tariff.
        raw_cents = Decimal(max_duration_ms) / Decimal(1000)
        reserve_cents = raw_cents.to_integral_value(rounding="ROUND_CEILING")
        amount = reserve_cents / Decimal(100)
        key = (tenant_id, run_id)
        with self._lock:
            if key in self._active or key in self._finished:
                raise ValueError("run identity already used")
            if tenant_id not in self._available:
                raise ValueError("unknown tenant")
            if self._available[tenant_id] < amount:
                raise ValueError("insufficient budget")
            self._available[tenant_id] -= amount
            item = Reservation(tenant_id, run_id, amount, max_duration_ms)
            self._active[key] = item
            return item

    def settle(self, tenant_id: str, run_id: str, duration_ms: int, billable: bool) -> Decimal:
        if type(duration_ms) is not int or duration_ms < 0 or type(billable) is not bool:
            raise ValueError("invalid settlement")
        key = (tenant_id, run_id)
        with self._lock:
            item = self._active.get(key)
            if item is None:
                raise ValueError("missing or already settled reservation")
            if duration_ms > item.max_duration_ms:
                raise ValueError("execution exceeded authorized maximum")
            # Settlement uses cent precision for the prepaid pilot. Fractional
            # cents should instead be aggregated in a durable invoice ledger.
            raw = Decimal(duration_ms) / Decimal(1000) * USD_PER_SECOND if billable else Decimal(0)
            charged = raw.quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
            if charged > item.reserved_usd:
                raise ValueError("charge exceeds reservation")
            self._available[tenant_id] += item.reserved_usd - charged
            del self._active[key]
            self._finished.add(key)
            return charged

    def available(self, tenant_id: str) -> Decimal:
        with self._lock:
            return self._available[tenant_id]
