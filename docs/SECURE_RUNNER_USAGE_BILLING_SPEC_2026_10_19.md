# Koschei Secure Runner — Usage Billing Contract (proposal, 2026-10-19)

Status: **SPEC ONLY; NOT IMPLEMENTED OR PRODUCTION-READY.** This document does not change `ks run` or implement a billing API.

## Rate and unit

Standard-class execution: **USD 0.01 per elapsed execution second** (USD 0.00001 per millisecond). CPU/memory limits for the class must be validated and published before taking payments. Measure monotonic elapsed time **inside the runner execution boundary**, excluding queue delay, authentication, payment processing and cold-start platform overhead when possible; record measurement boundaries precisely. Wall-clock duration is **not** equivalent to CPU-seconds.

For each tenant's billing period, aggregate eligible integer milliseconds, then compute USD cents as `total_eligible_ms / 1000`. Do not round each run to a whole second. Use integer milliseconds and decimal arithmetic, not binary floating-point money. Round only the final invoice to two decimal USD places under an explicitly published rounding rule.

Examples: 250ms = $0.0025 before invoice rounding; 1000ms = $0.01; 60000ms = $0.60. Small charges accumulate in the billing ledger, not in per-run card payments.

## Billable state machine

`queued -> running -> succeeded | guest_failed | guest_timeout | host_failed | cancelled`.

- `succeeded`: eligible execution milliseconds.
- `guest_failed` (guest exception / invalid program after execution begins): eligible execution milliseconds, provided customer was informed.
- `guest_timeout`: eligible measured time **up to the published execution ceiling**, never unbounded; report reason.
- `host_failed` (platform outage, runner fault): no charge.
- `queued`, rejected validation/authentication, or cancelled before start: no charge.
- `cancelled` after start: charge elapsed guest runtime only if clearly disclosed and metering is reliable; otherwise no charge during pilot.

Each attempt must have unique immutable `run_id`, tenant/project ownership, metering start/end, `duration_ms`, result classification, charge eligibility and tariff version. Replay must not double bill; ensure idempotent ledger entry key `(run_id, tariff_version)`. Changes to classifications require auditable adjustments, not edits to immutable history.

## Budget enforcement

Set customer-configurable monthly spend ceiling and per-run max duration; reject **before starting** a run if the remaining prepaid/authorized budget cannot cover the configured max runtime. Reserve worst-case funds/credits atomically before dispatch, settle on measured time, release unused reserve. Parallel runs must not overspend via race conditions. For postpaid invoicing, require a separate credit-risk policy. Do not claim a strict spend cap without concurrency and reservation tests.

## Security requirements

**PROTECTS AGAINST:** Duplicate billing from retries, unintended unbounded billed execution, cross-tenant usage reads, charges for platform faults, *when implemented and tested*.

**DOES NOT PROTECT:** Guest escape, arbitrary network access, data exfiltration, malicious host operator, hypervisor compromise or inaccurate time measurement. WASM import inventory alone is not a sandbox.

**ASSUMPTIONS:** Verified WASI isolation, external CPU/memory/wall-time enforcement, trusted monotonic clock, durable atomic ledger, authenticated tenant identity, separately secured payment processor.

**FAILURE MODE:** On missing meter, ambiguous exit classification, corrupted ledger, insufficient reservation, or incomplete audit evidence, fail closed: reject new run or mark nonbillable pending review. Do not silently estimate and charge.

## Release gates

1. CI resource-limit tests and real runner integration tests pass; no-preopen/no-env/no-network policy verified with negative fixtures.
2. Ledger unit tests: 250ms, 750ms, 1000ms, zero ms, guest fault, host fault, timeout, cancellation, retries and parallel reservations.
3. Tenant-isolation API tests and immutable reconciliation audit pass.
4. Actual infrastructure unit economics measured before finalizing CPU/memory class and quota.
5. Explicit go/no-go review before processing customer workloads or payments.
