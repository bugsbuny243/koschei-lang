# Strange Native Admission V1

**Status:** opt-in, authority-free attestation proof prototype. Not a production
runtime gate, not an HSM/MPC signature authorization policy.

## Why it exists

PR #318 binds generated native representation *source* to a 120-second window.
A source hash alone does not authorize a compiled executable. This companion
prototype binds an externally attested **native binary hash** to that source
hash, one deployment/Veyra, canonical MIR, a Continuity source, epoch and time
window. It rejects mismatched native bytes, claims, and expired windows.

## Mandatory trusted deployment assumptions

1. **Independent trusted builder:** verifies canonical MIR, exact source, compiler,
   toolchain and build provenance, then supplies the exact native binary.
2. **Attestation custody:** the attestation key is separate from representation
   seed, inaccessible to the workload and bound to the Trust Plane. Python
   caller-supplied keys are only a bootstrap API, **not hardware proof**.
3. **Continuity/time:** epoch and seconds must be monotonic, durable,
   rollback-resistant and independently sourced. The provided Python readers
   do not provide those properties.
4. **Runtime/code identity:** a real process must measure its *running* binary
   and enforce this check in an unbypassable compartment before privileged
   requests. This prototype only verifies bytes explicitly provided to it.
5. **No authority promotion:** a valid attestation means only that specified
   bytes correspond to the asserted build binding. It is NOT permission to
   sign, transfer, access a secret, materialize a Galaxy, or bypass 6/6 Sathra.

Both issuer and verifier re-check the Continuity epoch and wall-clock window
after their work; if the window closes during hashing, admission fails closed.

## Test invocation

`python -m unittest discover -s tests -p 'test_strange_native_admission_v1.py' -v`

## Unfinished production gates

- independent source->binary build reproducibility and verifiable compiler chain;
- actual live process measurement, isolated enforcement/TPM/TEE/HSM integration;
- physical trust-domain separation and durable replay/epoch fencing;
- automatic two-minute release/restart/handoff with in-flight request guarantees;
- provenance-preserving manifests with a non-exportable attestation key;
- cross-tenant failure-root compromise exercises.

This module does not change public `ks build` or existing execution gates.
