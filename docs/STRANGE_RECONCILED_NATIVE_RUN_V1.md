# Strange Reconciled Native Run v1

**Status: opt-in local crash-aware orchestration bootstrap. NOT trusted production execution.**

This driver composes two independently reviewed prototype components:

- PR #328's activated-epoch native admission and Linux sealed memfd supervised worker.
- PR #329's durable launch attempt and runner-report journal in the same SQLite Continuity database.

## Contract

1. Verify typed pending native candidate input and a per-call monotonic seconds reader.
2. Before spawning anything, atomically claim one launch attempt for the exact
   authenticated activated next epoch, handoff MAC and native SHA-256.
3. Call the existing activated-native runner, which independently recomputes the
   active canonical MIR-Go source, native admission and running epoch window.
4. If the supervised worker ends with code 0 and the expected epoch/native
   identity, record an authority-free runner-reported OK outcome. A late success
   report is rejected if the epoch has ended or advanced.
5. On a worker failure, wrong exit code or byte identity mismatch, record the
   attempted run as FAILED when possible.
6. If the result cannot be recorded (crash, outage, rollback, unknown status),
   leave CLAIMED unresolved and **never automatically retry** or restore the
   prior epoch. Only a fresh eligible epoch and separately reviewed handoff
   may receive another launch claim.

## Coverage

Integration tests execute a real precompiled Koschei/MIR-Go native binary in
Linux after its epoch is activated and verify exact stdout plus a durable
REPORTED_OK record. Negative tests cover preactivation denial, wrong candidate,
runner denial, nonzero native exit, late positive report, crash between run
and recording, restart persistence and concurrent duplicate launches.

## Limitations

- The SQLite claim is **not atomic with fork/exec or remote effects**. A crash
  between claiming and starting the process leaves an unresolved CLAIMED entry
  indistinguishable from a crash after starting. Thus this is not exactly-once
  execution.
- All outcome values are reported by the local Python process rather than a
  protected hardware monitor. A compromised host can forge results, bypass
  the driver, invoke the old APIs, or roll the database back.
- Only a single local SQLite database is coordinated. This does not provide
  multi-node agreement, non-exportable attestation keys or trusted time.
- Already running workers can act between the supervisor's epoch polls or
  escape the original process group. No secure isolation, emergency credential
  revocation, in-flight request recovery or zero-downtime cutover is proven.
- Every report/result is authority=False; no Library secret, Khar/Sathra
  approval, wallet signer or privileged effect is exposed here.
- The future binary must still have trusted external source->binary provenance;
  a SHA-256-pinned Go launcher alone is insufficient.

## Tests

`python -m unittest discover -s tests -p 'test_strange_reconciled_native_run_v1.py' -v`

This code sits on a preparation branch while PR #328 and PR #329 finish
exact-head canonical GitHub CI. It must be rebased/copy-ported onto the
merged `main` before creating a separate PR.

Tracked in issue #317.
