# Strange Pending Epoch Projection V1

**Status: opt-in next-window source preparation, without execution authority.**

Current `project_strange_epoch_go_v1` rejects a future epoch. However a
candidate must be prepared *before* a 120-second boundary if the eventual
rollout is to avoid a compile-time gap. This module addresses that specific
builder limitation only.

## Preconditions

- The current Continuity epoch and canonical 120-second start must match a
  locally durable `StrangeDurableContinuityV1` snapshot.
- The current window must still be live, and the external seconds source must
  never move backward during the preparation call.
- Only `current_epoch + 1` and `current_start + 120` are derivable in
  this interface, never an arbitrary future epoch.
- The same private seed, MIR fingerprint, Veyra and deployment are used in the
  domain-separated derivation already required by the active Strange projector.

## Outcome

Returns source plus **PendingStrangeProjectionV1** with the future source
digest, exactly next epoch/start/expiry, and `authority=False`. The pending
type is deliberately not `StrangeEpochProjectionV1`; the native attestation
issuer rejects it even if a caller tries to submit it directly.

After the real Continuity epoch advances, a trusted builder must revalidate
the exact canonical MIR source and output bytes, and obtain a fresh active
attestation. Tests prove the pending generated source is byte-for-byte equal
to the active source generated after the epoch transition.

A pending projection can help feed a **separate** candidate build-and-stage
pipeline, but this module does not call the Go compiler, issue HMAC native
attestations, store candidate bytes in SQLite or perform process handoff.

## Important limits

- This builder is a Python prototype using a caller-supplied seed/time source.
  It does not prove hardware custody, trusted monotonic time or anti-rollback.
- It does not stop running processes, coordinate old/new workers, prove zero
  downtime, isolate operating-system trust, or authorize remote signing.
- It does not close the older low-level native attestation issuer bypass.
- The local Continuity `advance` method remains separately callable, and
  production still requires a single protected epoch writer service.

## Tests

`python -m unittest discover -s tests -p 'test_strange_pending_epoch_projection_v1.py' -v`

Tests include source equivalence before/after activation, cross-tenant and
Veyra/seed separation, old/next epoch boundary, current epoch drift mid-build,
untrusted clock rejection and attestation type isolation.

Related: PR #326 metadata handoff and issue #317.
