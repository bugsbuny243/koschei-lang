# Strange Cutover Orchestrator v1 — fail-closed two-phase local coordinator

**Status:** prototype composition of existing v1 primitives. **Not** production
trust attestation, process isolation, global leader election or key custody.

## Interfaces

`koschei/strange_cutover_orchestrator_v1.py` exposes:

1. `prepare_and_stage_next_epoch_v1(...)` validates the active
   `StrangeDurableContinuityV1` 120-second slot, builds only the immediately
   following epoch via `prebuild_next_strange_native_v1`, then invokes
   `StrangeEpochHandoffV1.stage` in the existing SQLite
   `BEGIN IMMEDIATE` transaction. The return value
   `StrangeStagedCutoverV1` carries the in-memory native bytes and a durable
   HMAC-bound handoff identity. It is **not** an execution grant.
2. `activate_and_reconcile_cutover_v1(...)` admits only
   `[next_start, next_start + 120)`. It checks candidate fingerprints,
   pinned compiler SHA-256, continuity identity, staging state, and clock
   monotonicity within the invocation and relative to prepare time. Then
   `StrangeEpochHandoffV1.activate` atomically activates the new epoch and
   tombstones the predecessor. Only after a successful commit does
   `run_reconciled_prebuilt_strange_native_v1` request a durable
   once-only launch claim and reconcile observed worker outcome.

## Denial and crash semantics

- **Replay:** duplicate stage or repeated activation fails closed. Launch
  claims remain authoritative for whether a candidate may run again.
- **HMAC tamper:** mutation of staged candidate or handoff MAC prevents
  activation. The activated candidate is re-verified by the existing runner.
- **Clock rollback:** same-phase decreases and activation time earlier than
  preparation are denied. A separately trusted monotonic clock must be supplied;
  Python and SQLite cannot prove independent time authority.
- **Crash after activation:** the epoch may be committed before a launch
  succeeds or reports. Never roll Continuity backward or blindly retry.
  Inspect `strange_launch_attempts_v1` (via the durable reconciliation API)
  and the operator evidence. Unknown `CLAIMED` states are not success.
- **Artifact lifetime:** SQLite stores hashes and HMAC, **not** native bytes,
  signing keys or the Trust Plane seed. After restart, the exact prebuilt
  native bytes must be reacquired from a separately authenticated artifact
  store; the coordinator does not invent recovery or silently rebuild.
- **Local scope:** a database transaction does not provide distributed
  consensus or prevent privileged host/database tampering. It does not confer
  wallet, Khar/Sathra, signer or other effect authority.

## Verification

Run:

```sh
python3 -m unittest discover -s tests -p 'test_strange_cutover_orchestrator_v1.py' -v
python3 -m unittest discover -s tests -p 'test_*.py'
```

The dedicated unit tests mock the compiler and native launcher while using
real SQLite stage/activation records. Existing Strange integration tests
exercise the actual Go builder and Linux memfd supervised execution.

## Real native integration evidence

`tests/test_strange_cutover_orchestrator_integration_v1.py` runs on Linux
with Go available. It compiles the actual future-epoch artifact using the
SHA-256 pinned local Go binary, stages and activates the SQLite handoff,
launches through the existing sealed memfd supervised native path, asserts
`REPORTED_OK` durable once-only reconciliation and rejects second activation.
This is stronger than a mocked orchestration test, but it is still a local
Linux prototype, not independent clock, signing-key or OS integrity attestation.

```sh
python3 -m unittest discover -s tests -p 'test_strange_cutover_orchestrator_integration_v1.py' -v
```
