# KOSCHEI REMOTE ATTESTATION EVIDENCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PROVIDER-NEUTRAL RAW EVIDENCE BINDING / HARDWARE VERIFIER ADAPTERS PENDING

## PURPOSE

`BuilderEnvironmentAttestationV1` must not be backed only by a local Koschei HMAC. V1 adds a provider-neutral remote-attestation evidence receipt over opaque raw evidence bytes, canonical environment/workload measurements, a trust-root identity and freshness window.

Sanctioned path:

`raw TPM / TEE / cloud evidence bytes`
`-> trusted provider-specific verifier outside generic Lang core`
`-> RemoteAttestationEvidenceV1`
`-> BuilderEnvironmentAttestationV1`
`-> VerifierBuilderObservationV1`
`-> two-builder reproducibility receipt`
`-> reproducible runtime admission`

## REMOTE EVIDENCE

`RemoteAttestationEvidenceV1` binds:

- provider id,
- trust-root id,
- exact raw evidence digest,
- environment measurement digest,
- workload measurement digest,
- observed epoch,
- expires-before epoch,
- verified=true,
- authority=false.

The receipt is authenticated under a dedicated remote-attestation verifier key.

## FRESHNESS

Evidence is valid only when:

`observed_epoch <= current_epoch < expires_before_epoch`

Future and stale evidence fail closed. Boolean epochs are rejected.

## BUILDER ENVIRONMENT HANDOFF

`BuilderEnvironmentAttestationV1` now requires remote evidence. Its environment and workload measurements must exactly match the measurements in the remote evidence, and it carries the remote-evidence digest plus trust-root id.

`VerifierBuilderObservationV1` binds the remote-attestation evidence digest in addition to toolchain and builder-environment provenance.

## DISTINCT TRUST ROOT POLICY

The reproducible-build verifier supports an optional policy:

`require_distinct_trust_roots=True`

When enabled, builder A and B cannot share the same remote-attestation trust-root identity.

This is policy, not a universal rule: some deployments may legitimately use different machines under one cloud/TEE root.

## PROTECTS AGAINST

- local builder-environment HMAC being treated as sufficient remote attestation,
- raw attestation evidence rebinding,
- environment/workload measurement mismatch between remote evidence and builder attestation,
- trust-root relabeling without verifier key,
- stale or future remote evidence,
- dropping remote-evidence identity from builder observations/reproducibility receipts,
- optionally counting two builders under one trust root where policy forbids it.

## DOES NOT PROTECT AGAINST

- a buggy or malicious provider-specific attestation verifier,
- compromised remote-attestation verifier key,
- compromised or malicious hardware/cloud attestation root,
- fake measurements accepted by an upstream verifier,
- two distinct attested environments controlled by one attacker,
- shared hypervisor/firmware/host compromise,
- measure-A/execute-B runtime TOCTOU.

## ASSUMPTIONS

- provider-specific adapters perform real signature/certificate/quote verification before issuing this generic receipt,
- trust-root identities are pinned by deployment policy,
- epoch/freshness state is monotonic at the authoritative boundary,
- raw evidence bytes are the exact bytes verified by the provider-specific adapter.

## FAILURE MODE

This module does not itself parse TPM quotes, Intel/AMD TEE reports or cloud attestation documents. If a caller simply wraps arbitrary bytes and possesses the trusted verifier key, the receipt can lie. Therefore `RemoteAttestationEvidenceV1` is an authenticated bridge for real attestation verification, not a substitute for it.

## NEXT

1. Define provider-neutral attestation-verifier ABI and revocation/root policy.
2. Implement at least one real hardware/cloud adapter outside Lang core and feed its verified result into this contract.
3. Bind builder keys to attested workload identity.
4. Add durable monotonic freshness/replay state.
5. Close runtime load-handle TOCTOU.
