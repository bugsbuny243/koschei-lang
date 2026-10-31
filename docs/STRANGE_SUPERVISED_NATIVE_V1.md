# Strange Supervised Native v1 — local epoch lifecycle

**Status: opt-in Linux process supervisor prototype. Not a Trust Plane, sandbox,
independent signer, or guarantee of instantaneous privilege revocation.**

Prior Strange modules bind a native artifact to an exact epoch and launch its
verified bytes from a sealed anonymous memfd, but a launched process can remain
alive after expiry. The opt-in `run_strange_supervised_native_v1` adds a bounded
local lifecycle around that existing verifier.

## Implementation

1. Verify native hash, attestation, Veyra/deployment/MIR and the current
   durable SQLite Continuity epoch/window.
2. Copy to a sealed Linux memfd; verify exact bytes and re-admit the current
   epoch immediately before launch.
3. Spawn a **new process group** with minimal environment, no CLI arguments,
   stdin disabled and no inherited keys. Capture output in temporary files
   rather than unbounded in-memory pipes.
4. Poll local Continuity and trusted seconds at a bounded interval (default
   50 milliseconds) while the process runs; reject if epoch changes, T=120
   expires, stdout/stderr exceed their bounded limits or a monotonic local
   deadline is reached even when the external clock is frozen.
5. Send SIGKILL to the direct child process group on rejected liveness or
   timeout, wait for the child to terminate, and close the sealed descriptor.
6. A successful completion only returns a local `authority=False` observation.

No existing public `ks` commands or privileged execution APIs are changed.

## Security limitations

- A polling supervisor can observe epoch changes only at its sampling
  intervals. A native process may act in between polls. **Zero-delay cutover
  and atomic at-effect fencing are not proven.**
- A subprocess can spawn children, alter session/process-group membership,
  or exploit the host. Killing one process group is **not reliable containment**
  of every descendant. Production needs Linux cgroups, isolated process
  credentials, a native supervisor and a separately enforced policy.
- A process launched before expiry may perform actions before it is killed.
  No sensitive credentials or permissions are released to these workers.
- Local monotonic wall-runtime bounding is not a hardware trusted clock;
  the caller-supplied seconds reader and SQLite state are not rollback proof.
- The separate `AtomicExecutionCoordinator`, Khar/Sathra proof gates and
  remote signers remain unbound to this supervisor. **This module grants
  no critical effect authority and cannot protect private Library secrets.**
- A worker killed at epoch expiry is **not automatically replaced** by a
  new compiled representation. A verified green/blue handoff and in-flight
  request recovery still need their own tests.

## Tests

`python -m unittest discover -s tests -p 'test_strange_supervised_native_v1.py' -v`

Covers native MIR-Go output parity, tampered artifacts, wrong Veyra, pre-launch
expiry, live epoch advance, live clock expiry, frozen clock with monotonic
deadline, and malformed supervision bounds.

Tracked under GitHub Issue #317.
