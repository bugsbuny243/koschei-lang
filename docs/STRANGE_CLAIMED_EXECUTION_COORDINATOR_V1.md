# Strange Claimed Execution Coordinator v1

**Status: opt-in local crash-visible execution coordination. Not a privileged
Trust Plane, hard OS process isolation, zero-downtime handoff, or exactly-once
remote effect system.**

This prototype connects the earlier non-authoritative epoch-native launch API
(PR #328) with the durable single-attempt reconciliation journal (PR #329).
It keeps both low-level components unchanged, and makes failure reporting part
of this single optional code path.

## Sequence

1. Check sealed canonical MIR, typed pending-native artifact and a local
   monotonic-in-call trusted seconds source.
2. In the **existing Continuity SQLite database**, reserve one launch attempt
   with `BEGIN IMMEDIATE`. The journal validates the activated next epoch,
   HMAC-bound handoff, retired old epoch, native SHA256 and current window.
3. Only after the claim is committed, invoke the activated-candidate launcher,
   which itself rechecks the canonical MIR-Go source, the actual native bytes,
   deployment/Veyra, epoch and signed native evidence before running the
   binary in a supervised sealed Linux memfd.
4. Validate the returned local observation: exit code must be zero; native
   SHA256 and observed epoch must exactly match the claimed candidate;
   `authority` must be false.
5. Authenticate and record the **runner-reported** result as
   `REPORTED_OK` or `REPORTED_FAILED`. On a failed native run, record a
   failed result without moving Continuity back to its old epoch.
6. If the local report cannot be written, leave the claim in `CLAIMED`.
   Never make an automatic second launch attempt; an operator must reconcile
   the unknown outcome.

A successful return contains a local worker observation and a durable
reconciliation record, both explicitly **non-authoritative**.

## Fail-closed tests

- Launch before activation cannot create an attempt or invoke the runner.
- Valid in-window execution records one `REPORTED_OK`; a replay is denied.
- Failed process, wrong epoch or wrong native digest records a failure.
- Report write failure leaves `CLAIMED` and cannot be retried automatically.
- Epoch advancement before success reporting prevents stale success.
- Failure reported after epoch rotation remains visible without rollback.
- Wrong handoff key, altered candidate, expired clock and concurrent requests
  cannot produce multiple launches.
- On Linux with Go installed, a real sealed canonical MIR-Go candidate can be
  prepared, staged, activated, run and reconciled in one integration test.

## Explicit limits

- `claim_once` cannot atomically cover Linux process creation/termination,
  external effects, remote signing or in-flight request transfer. An
  unprivileged worker could still act before a failed outcome is observed.
- The record is local SQLite only; not distributed consensus, trusted
  monotonic hardware time or anti-rollback storage.
- Neither success report nor HMAC authenticates the **running process**;
  the caller can bypass these Python entrypoints. The low-level issuer and
  launch routines are still callable outside this coordinator.
- A separate protected Trust Plane must own native key custody, exclusive
  epoch advancement, running-process measurement, isolation, signer policy
  and **atomic at-effect** authorization. No Library secrets, wallet keys,
  Khar/Sathra permission or privileged-effect approval may be provided here.
- This is not automatic 120-second deployment or a zero-downtime green/blue
  cutover. External orchestration and recoverable request draining remain
  outstanding.

## Focused verification

`python -m unittest discover -s tests -p 'test_strange_claimed_execution_coordinator_v1.py' -v`

Only promote to `main` after the exact-head full canonical GitHub CI and
P0 checks pass. Tracks Issue #317.
