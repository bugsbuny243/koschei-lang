# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / ABI + REPRODUCIBLE SIGNED-TOOLCHAIN VERIFIER ADMISSION WIRED / PROVIDER NETWORK ADAPTER REMAINS EXTERNAL

## PURPOSE

`effect-completed` is local. Provider finality must be derived from raw provider bytes through a known verifier contract, not from caller-selected state/reference/proof.

Sanctioned path:

`local effect result bytes`
`-> sealed ProviderAdapterAbiV1`
`-> VerifiedIrBuildInputV1`
`-> signed ToolchainProvenanceV1`
`-> two authenticated builder observations`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> raw provider response bytes`
`-> trusted provider-native verifier`
`-> ProviderNativeVerificationReceiptV1`
`-> receipt-bound provider verdict`
`-> finality attestation`
`-> ExternalFinalityProofEnvelopeV1`

## VERIFIER ADMISSION

The provider-native verifier callback cannot run with base artifact admission alone. The sanctioned API requires the reproducibility-gated admission that proves two distinct builder observations agreed on the exact verifier artifact.

Builder observations no longer accept arbitrary toolchain digests. Each observation must bind authenticated `ToolchainProvenanceV1` backed by exact toolchain artifact bytes and a protected signing key.

The build provenance toolchain must also appear in the reproducible builder evidence before runtime admission.

## PROVIDER ADAPTER ABI

`ProviderAdapterAbiV1` binds provider id, adapter id, schema id/version, verifier implementation digest and authority=false. The implementation digest must match exact runtime-admitted verifier artifact bytes.

## NATIVE VERIFICATION RECEIPT

The native receipt binds:

- adapter ABI digest,
- verifier implementation digest,
- base runtime admission digest,
- reproducibility receipt digest,
- reproducible runtime admission digest,
- exact effect envelope/measurement,
- raw provider response digest,
- expected and verified external reference,
- provider proof,
- observed epoch and state.

## V1 REFERENCE CONTRACT

Successful effect callback bytes are the canonical expected external reference. Pi payment V1 uses canonical txid bytes. Provider-native verification must return the same canonical reference or fail before verdict issuance.

## PROTECTS AGAINST

- caller-selected provider finality state/reference/proof,
- raw provider response rebinding,
- using a different external reference than the measured effect,
- verifier ABI relabeling,
- provider verification without two-builder reproducibility gate,
- caller-selected toolchain digest in sanctioned builder/build provenance path,
- relabeling verifier evidence under another signed toolchain identity,
- dropping reproducibility identity from finality provenance.

## DOES NOT PROTECT AGAINST

- malicious/buggy verifier implementation that is legitimately built and admitted,
- intentionally signed malicious compiler/toolchain,
- compromised toolchain/builder/runtime/finality keys,
- common-mode compiler defects across independent builders,
- unauthenticated provider transport accepted by verifier,
- provider reorg/reversal,
- host/runtime compromise or replay-state rollback,
- measure-A/execute-B runtime TOCTOU.

## ASSUMPTIONS

- toolchain signing authority is protected,
- signed toolchain bytes are the actual compiler/toolchain bytes used by builders,
- builder identities represent independent build authorities,
- runtime executes exact admitted verifier bytes,
- provider-native verifier performs real authenticated provider verification,
- final consumers validate full ExternalFinalityProofEnvelopeV1.

## FAILURE MODE

Signed and reproducible does not mean correct. A malicious signed compiler or common-mode compiler defect can produce the same malicious verifier artifact across independent builders. The trust model therefore still needs environment attestation, revocation policy and stronger compiler correctness evidence.

## NEXT

1. Bind builder identities to independently attested build environments.
2. Add epoch/revocation policy for toolchain, builder, verifier artifact and ABI trust.
3. Add immutable runtime load-handle identity to close measure-A/execute-B TOCTOU.
4. Explore diverse-compiler/self-rebuild verification.
5. Pin exact supported Pi backend/payment schema before production parser implementation.
