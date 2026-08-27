# KOSCHEI ATTESTATION VERIFIER ABI V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / ABI-BOUND REMOTE ATTESTATION VERIFIER / PROVIDER PARSER EXTERNAL

## PURPOSE

Remote-attestation evidence is not trustworthy merely because a caller supplies a trust-root id, environment measurement or freshness window. The sanctioned V1 path binds one provider-neutral verifier ABI to exact verifier artifact bytes and derives canonical attestation facts only from that verifier callback result.

`raw attestation bytes`
`-> AttestationVerifierAbiV1`
`-> exact verifier artifact measurement`
`-> provider-specific verifier callback`
`-> RemoteAttestationVerificationResultV1`
`-> RemoteAttestationEvidenceV1`
`-> BuilderEnvironmentAttestationV1`

## ABI

`AttestationVerifierAbiV1` binds:

- attestation provider id,
- evidence-format id,
- schema version,
- exact verifier implementation digest,
- authority=false.

The implementation digest is domain-separated SHA-256 over exact verifier artifact bytes.

## SANCTIONED ISSUANCE

`verify_remote_attestation_with_abi_v1(...)` verifies the ABI and artifact identity before invoking the verifier callback. The caller does not separately supply:

- trust-root id,
- environment measurement,
- workload measurement,
- observed epoch,
- expiry epoch.

Those values are returned by `RemoteAttestationVerificationResultV1` and sealed into `RemoteAttestationEvidenceV1` together with the ABI digest and verifier implementation digest.

## PROTECTS AGAINST

- relabeling which verifier implementation processed raw attestation evidence,
- running a different verifier artifact under an existing ABI identity,
- caller-selected trust-root/environment/workload/freshness values on the sanctioned path,
- dropping verifier ABI identity from the resulting remote evidence,
- verifier callback execution when the supplied artifact differs from the ABI measurement.

## DOES NOT PROTECT AGAINST

- malicious or buggy verifier code whose artifact is nevertheless admitted,
- compromised verifier key or ABI admission authority,
- malicious attestation trust roots,
- incorrect TPM/TEE/cloud parser logic,
- upstream firmware/hypervisor compromise,
- replay if freshness/nonce policy is insufficient,
- semantic correctness of the verifier artifact merely from its hash.

## ASSUMPTIONS

- the provider-specific verifier actually validates signatures/certificates/quotes according to the provider format,
- ABI identity is reviewed before admission,
- verifier artifact bytes measured are the bytes executed,
- remote-attestation verifier keys are protected,
- lifecycle epoch is trusted.

## FAILURE MODE

An ABI binds identity, not correctness. A malicious verifier can consistently return false trust roots and measurements while still producing cryptographically valid Koschei receipts if that verifier is admitted. V1 therefore must not be described as implementing TPM, Intel TDX, AMD SEV-SNP or cloud attestation verification by itself.

## NEXT

1. Bind attestation-verifier artifact admission to the same Verified-IR/reproducible-build provenance model without recursive trust collapse.
2. Add root allowlists, revocation and epoch policy.
3. Bind provider nonce/challenge freshness where the native format supports it.
4. Implement one real provider-specific adapter outside Lang core.
5. Close verifier measure-A/execute-B TOCTOU with immutable load handles.
