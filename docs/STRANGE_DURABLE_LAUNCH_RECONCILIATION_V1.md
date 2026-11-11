# Strange Durable Launch Reconciliation V1

**Status: local SQLite attempt/report journal. NOT an execution lock, signer
gate, runtime isolation, or production rollback mechanism.**

Existing Strange components can prepare next-epoch Go/native bytes, activate
a staged HMAC-bound candidate, and explicitly run the prepared binary under
an epoch-polling Linux supervisor. Failure to start, process exit and crashes
still need a durable operator-visible reconciliation record.

## What this adds

A local journal shares the *same SQLite database* as Continuity and the
atomic handoff. Each `(continuity_id, next_epoch)` can be **claimed once**.

- `claim_once` holds `BEGIN IMMEDIATE` and reads the exact active epoch,
  canonical start, HMAC-authenticated activated handoff, previously retired
  old epoch, proposed native SHA256 and current time while holding the lock.
- Duplicate or concurrent claims fail even after restart. A crash leaves
  `CLAIMED`, requiring operator investigation instead of automatic retry.
- `record_result` accepts a **runner-reported** boolean exactly once,
  but requires the protected handoff key to recompute the staged candidate's
  MAC; merely reading the exposed MAC from SQLite cannot authenticate a report.
  `REPORTED_OK` requires the same active, unexpired epoch at report time.
  `REPORTED_FAILED` can be recorded after expiry/rotation, so failures
  remain visible to the operator.
- The state records contain **no executable bytes, secret seeds, signing
  keys, passwords or privileged operation approvals.** Every record has
  `authority=False`.

## Recovery contract

If the new binary cannot be started, the safe default is **fail closed**.
Do not restore the old Continuity epoch: old native evidence is stale and
could revive replay and signing risks. Record the failed or unresolved
attempt. A fresh eligible epoch and separately authenticated candidate are
required for another launch attempt.

An `REPORTED_OK` observation is a caller's claim, not proof that a process
is healthy, still running, or has been securely attested. A crash after
recording a claim and before actual OS launch cannot be distinguished from
a crash after launch by SQLite alone. The journal intentionally refuses
automatic re-execution.

## Production boundaries

- The existing launch API does **not** require calling this journal; Python
  entry points and low-level epoch/attestation interfaces remain bypassable.
  Production must enforce one independently protected orchestrator endpoint.
- The record is not atomic with `fork`, `exec`, process shutdown or
  critical remote effects, and cannot establish exactly-once execution.
- No distributed consensus, hardware-backed trusted time, HSM/TPM custody,
  no-rollback storage, sandbox or emergency credential revocation exists.
- Old-process termination remains polling-based; no recovery of in-flight
  work or zero-downtime failover is implemented.

## Tests

`python -m unittest discover -s tests -p 'test_strange_durable_launch_reconciliation_v1.py' -v`

Checks active handoff matching, one-time claims, concurrent local writers,
restart/crash persistence, bad stage keys/digests, late results, expiry,
clock regression and the refusal to roll Continuity backwards.

Issue #317 tracks the missing independent Trust Plane and hard effect gates.
