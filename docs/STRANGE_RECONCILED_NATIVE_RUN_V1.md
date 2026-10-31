# Strange Reconciled Native Run V1

**Status: opt-in local Linux bootstrap with persistent one-attempt reporting.
NOT an at-effect authorization gate, trusted execution enclave or distributed
exactly-once service.**

This integrates the active prepared-native worker launch (#328) with the local
durable attempt journal (#329).

## Flow

1. An HMAC-authenticated next-epoch candidate has already been staged and
   activated in the durable Continuity SQLite journal.
2. `run_reconciled_prebuilt_strange_native_v1` first calls
   `StrangeDurableLaunchReconciliationV1.claim_once` under the same canonical
   SQLite database. This checks epoch, current half-open 120-second window,
   exact candidate native SHA256, stage key and retired predecessor and
   reserves at most **one attempt for this local Continuity epoch**.
3. It calls the existing activated prepared-native launcher. That launcher
   separately validates sealed MIR, canonical source identity, native byte
   digest, active native attestation and runs the exact binary from a sealed
   Linux memfd with live Continuity polling.
4. Normal, successful zero-exit completion and matching epoch/native identity
   lead to one `REPORTED_OK` record. A failure, exception, nonzero exit or
   mismatched observation leads to `REPORTED_FAILED`.
5. If the reporting transaction fails or time expires before a successful
   report, no success is returned and the record remains `CLAIMED`.
   Operators must investigate; no implicit retry or old-epoch rollback occurs.

The returned `StrangeReconciledNativeRunV1.authority` is **always false**.
Neither the report nor the child's stdout confers Khar, Sathra, Library,
Galaxy or signing rights.

## Tests

`python -m unittest discover -s tests -p 'test_strange_reconciled_native_run_v1.py' -v`

Tests cover a **real offline-Go prebuilt** canonical MIR program staged at
epoch 4, activated at epoch 5, sealed-executed and durably reported; simulated
worker failures, nonzero exit, wrong worker epoch/native digest, expired
success reporting, duplicate attempts, crash/restart and concurrent attempts.

## Security boundary

- The SQLite claim is **NOT atomically coupled to OS process spawn, signal
  delivery, external effects or a signer**. A crash after the claim leaves an
  ambiguous state; it deliberately rejects automatic execution retries.
- The launch API and low-level native HMAC issuer remain separately callable,
  so this optional wrapper is bypassable by an untrusted caller. Production
  requires mandatory isolated orchestration and restricted key custody.
- `REPORTED_OK` means a runner-reported observation, not independent
  process measurement or lasting service health. The worker may exit
  immediately after reporting, and no in-flight requests are migrated.
- Trusted monotonic time, cgroups, hardware-attested build provenance,
  anti-rollback storage, HSM/TPM signer, multi-node consensus and at-effect
  irreversible authorization remain external requirements.
- No automatic 120-second zero-downtime binary replacement is claimed.

Issue #317 tracks remaining production Trust Plane gates.
