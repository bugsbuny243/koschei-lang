# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / REPRODUCIBILITY-GATED PROVIDER PATH / NETWORK ADAPTER REMAINS EXTERNAL

## PURPOSE

`effect-completed` is local. Provider finality must be derived from raw provider bytes
through a known and reproducibly admitted verifier contract, not from caller-selected
state/reference/proof.

Sanctioned path:

`local effect result bytes`
`-> ProviderAdapterAbiV1`
`-> VerifiedIrBuildInputV1`
`-> two independent builder observations`
`-> VerifierReproducibleBuildReceiptV1`
`-> exact-artifact base runtime admission`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> raw provider response bytes`
`-> provider-native verifier`
`-> ProviderNativeVerificationReceiptV1`
`-> receipt-bound provider verdict`
`-> finality attestation`
`-> ExternalFinalityProofEnvelopeV1`

## REQUIRED VERIFIER ADMISSION

The provider-native verifier boundary no longer accepts base
`VerifierRuntimeAdmissionV1` by itself. It requires a
`VerifierReproducibleRuntimeAdmissionV1` authenticated under a separate gate key and
bound to the exact base admission and provider ABI.

The native verification receipt binds:

- provider adapter ABI digest,
- verifier implementation digest,
- base runtime admission digest,
- reproducibility receipt digest,
- reproducible runtime-admission digest,
- exact effect envelope and measurement,
- raw response digest,
- expected/verified external reference,
- provider proof, epoch and state,
- authority=false.

A receipt cannot be validated after swapping the reproducibility gate, base admission,
ABI, artifact identity, raw response, reference or provider state.

## PI PROFILE

Pi remains a provider-specific profile. Pi V1 requires the same reproducibility-gated
admission before its raw response verifier callback can run. Lang core still does not
invent a Pi backend JSON schema, wallet, consensus or settlement implementation.

## PROTECTS AGAINST

- caller-selected provider state/reference/proof after native verification,
- raw provider response rebinding,
- provider response referencing a different object than the measured local effect,
- using one receipt under another provider/schema/verifier ABI,
- sanctioned provider verification with only a single-builder/base runtime admission,
- dropping reproducibility receipt/admission identity from final finality provenance.

## DOES NOT PROTECT AGAINST

- malicious verifier logic reproduced identically by both builders,
- colluding builders or shared compromised toolchain,
- compromised build/reproducibility/admission/verifier keys,
- unauthenticated provider transport accepted by the verifier,
- provider reorg/reversal after its own finality semantics,
- measure-A/execute-B TOCTOU,
- host/runtime compromise or replay-state rollback.

## ASSUMPTIONS

- builder identities represent independent trust domains in production,
- verified-IR/build/reproducibility/runtime keys remain separated and protected,
- runtime executes the exact admitted artifact bytes,
- provider-native production API does not expose a lower base-admission bypass,
- provider verifier performs real provider-native validation,
- final consumers validate the full `ExternalFinalityProofEnvelopeV1`.

## FAILURE MODE

Reproducibility does not prove semantic correctness. Two builders can faithfully produce
the same malicious output when they share a compromised compiler/toolchain or malicious
verified input.

The sanctioned bootstrap path now enforces reproducible admission end to end, but a
production runtime would lose that property if it exposes a hidden alternate verifier
entry point or measures artifact A while actually executing artifact B.

## NEXT

1. Bind builders to independently attested environments.
2. Sign and verify compiler/toolchain provenance.
3. Close measure-A/execute-B with immutable load handles or equivalent native runtime custody.
4. Add epoch/revocation policy for builder, toolchain, artifact, ABI and verifier trust.
5. Pin an exact supported Pi provider schema before a production parser is admitted.
