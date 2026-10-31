# Strange Runtime Observation v1

Status: **integrated local admission prototype; no production execution control**

This module combines the **existing** local durable Continuity journal,
non-authoritative native artifact attestation, and a clock-bound 120-second
window. Its purpose is to check supplied native executable bytes against the
canonical epoch, window start, deployment, Veyra and MIR identity at the
point a caller *requests* observation.

## Fail-closed behavior

- Journal admission checks **both** epoch and canonical 120-second start.
- Native HMAC evidence must identify the exact supplied bytes and correct
  deployment/Veyra/MIR/source/epoch/window.
- A fresh reading of the same local Continuity journal and clock must succeed
  after verification; time rollback *during this call* fails closed.
- T=119 within an epoch is admitted; T=120 rejects the prior epoch.
- A false, missing, inconsistent or expired claim is rejected.
- Local SQLite state survives restart. This is **not** rollback-resistant
  trusted time, physical isolation, or multi-replica consensus.

## No silent promotion to authority

The return value has `authority=False` and is **unsigned**. It must never
be cached or accepted as a credential. Anyone who can instantiate Python
objects could forge it; only the trusted live verifier's code path matters.
An attacker able to bypass this Python function can bypass this prototype.

Passing this check cannot release Library secrets, authorize hot-wallet
transactions, issue a Khar proof, approve 6/6 Sathra, or substitute a signing
gate. In particular, verification is **NOT atomic with the later side effect**:
the epoch may change immediately after it returns.

## Production prerequisites

- Isolated native/TEE-backed runtime measurement of the **executing** bytes.
- Non-exportable Trust Plane attestation key; independently authenticated
  source-to-binary build provenance.
- Trusted durable monotonic time and epoch across all production nodes.
- Actual execution/signer boundary that repeats epoch+authorization checks
  at the moment of privileged-effect consumption, with durable single-use
  state and independent approval roots.
- Automatic 120-second deployment cutover/retirement and secure recovery.

This is a compositional checkpoint for [Issue #317](https://github.com/bugsbuny243/koschei-lang/issues/317),
not its completion.

## Tests

`python -m unittest discover -s tests -p 'test_strange_runtime_observation_v1.py' -v`
