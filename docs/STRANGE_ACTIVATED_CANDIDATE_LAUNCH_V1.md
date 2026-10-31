# Strange Activated Prebuilt Candidate Launch v1

**Status: opt-in Linux local process integration. NOT an automatic 120-second
zero-downtime cutover, HSM, secure enclave, or at-effect Trust Plane gate.**

Earlier stages implemented a separately prepared **future** Go/native artifact,
a durable HMAC-bound staged next-epoch candidate and a local supervised sealed
memfd runner. This module connects them **only after** the prepared epoch is
durably activated.

## Launch gate

1. Accept only a typed pending native result created during the previous
   epoch. Its structure, target consecutive epoch, pinned Go executable digest,
   and exact native bytes must be consistent.
2. Require a corresponding **ACTIVATED** handoff from the same durable
   Continuity identity and an old-epoch retirement tombstone. Recompute the
   HMAC of the staged deployment, source digest, MIR/Veyra identity and native
   digest using the separately supplied trusted handoff key.
3. Match pending artifact's exact native SHA256 and source SHA256 to the
   authenticated staged candidate. No candidate substitution is accepted.
4. Validate the live canonical Continuity epoch and 120-second time window,
   regenerate the active epoch's canonical Go representation from sealed MIR
   with the same private representation seed, and compare the source digest.
5. Only after all checks, issue the normal **non-authoritative** native HMAC
   evidence for the exact prepared binary in the now-current epoch.
6. Run the verified bytes in a sealed Linux memfd using the existing
   `run_strange_supervised_native_v1` function; that runner rechecks the
   active epoch immediately before launch and during the worker's lifetime.
7. Return an authority-free local execution observation. Failure to match
   staged identity, time, or native bytes stops before launching a worker.

## What is demonstrated

Integration tests compile the actual Koschei/MIR-Go binary *before* the
boundary, stage it, activate the next epoch, and then execute those exact bytes
from a sealed Linux memfd. A separate integration test keeps a **sleeping Go
fixture** running in old epoch under the existing supervisor, commits the
epoch change, confirms the old supervised worker is rejected/stopped, and
runs the prebuilt new worker. The sleeping fixture is not claimed to be
canonical MIR -> native build provenance and holds no privileged authority.
Negative cases test premature activation,
modified candidate, changed Go pin, wrong Veyra/deployment/seed/key, forged
handoff record, expired epoch and epoch rotation between attestation and run.

## What is NOT demonstrated

- Nothing here automatically starts or replaces workers. A trusted external
  orchestrator must call stage/activate/launch at the correct time.
- The previous worker is **not killed by this function**; it relies on a
  separate polling supervisor, which cannot provide instantaneous fencing.
- The stage key and native attestation key are supplied by a Python caller.
  Neither is a physically independent, non-exportable HSM/TPM root.
- The builder's pinned Go launcher digest does not attest all of the Go
  toolchain or host; the candidate bytes are only as trustworthy as the
  separately verified original build and protected key-custody service.
- A compromised issuer can call the low-level native issuer outside this
  pipeline. A mandatory Trust Plane must restrict that interface.
- A worker may execute an external effect between supervisor polls or escape
  its process group. **No wallet keys, Library secrets, Khar/Sathra permissions
  or privileged effect approvals** are supplied to the worker.
- No durable in-flight request transfer, zero-downtime rolling deployment,
  distributed epoch lock, hardware trusted clock, or anti-rollback is built.

## Test

`python -m unittest discover -s tests -p 'test_strange_activated_candidate_launch_v1.py' -v`

Tracked under GitHub issue #317.
