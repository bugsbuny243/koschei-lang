# KOSCHEI VERIFIER BUILD PROVENANCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / VERIFIED-IR BUILD INPUT + REPRODUCIBILITY-GATED PROVIDER PATH

## PURPOSE

Koschei binds verifier implementation identity to sealed native semantic/proof input,
exact artifact bytes, two independent builder observations, and runtime admission before
provider-native verification may run.

Sanctioned chain:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> builder A observation + builder B observation`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1`
`-> VerifierRuntimeAdmissionV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> ProviderNativeVerificationReceiptV1`
`-> provider finality provenance`

## VERIFIED IR BUILD INPUT

`VerifiedIrBuildInputV1` binds the sealed native MIR fingerprint, Universe plan digest,
native proof digest, Library proof digest and proof decision. The sanctioned build API
does not accept a caller-selected build-input digest.

## ARTIFACT + REPRODUCIBILITY

The exact verifier artifact bytes are domain-separated SHA-256 measured. Build
provenance, adapter ABI and base runtime admission must agree on that digest.

Two distinct authenticated builder identities must additionally bind the same
`VerifiedIrBuildInputV1` and produce the same artifact digest. Their agreement is sealed
into `VerifierReproducibleBuildReceiptV1` and then into
`VerifierReproducibleRuntimeAdmissionV1`.

Provider-native verification now requires the reproducibility-gated admission. Base
`VerifierRuntimeAdmissionV1` alone is insufficient on the sanctioned path.

The provider-native receipt and final external-finality envelope carry the
reproducibility receipt and gate digests so downstream provenance cannot silently drop
the two-builder requirement.

## PROTECTS AGAINST

- caller injection of arbitrary verifier build-input digest,
- rebinding build provenance to another sealed MIR/proof world,
- one builder alone declaring reproducibility,
- two builders disagreeing on artifact bytes,
- ABI claiming one verifier while different bytes are loaded,
- sanctioned provider verification with only base runtime admission,
- dropping reproducibility provenance from finality proof.

## DOES NOT PROTECT AGAINST

- malicious verifier semantics accepted by current native policy,
- two colluding or identically compromised builders,
- a shared compromised compiler/toolchain producing the same malicious artifact,
- false toolchain provenance,
- measure-A/execute-B runtime TOCTOU,
- host/runtime or protected-key compromise.

## ASSUMPTIONS

- native MIR/proof validation remains fail-closed,
- production builder identities represent genuinely independent trust domains,
- build/reproducibility/runtime keys remain separately protected,
- runtime executes exactly the bytes it admitted,
- production exposes no lower provider-verification bypass.

## FAILURE MODE

Reproducibility proves independent agreement on bytes, not semantic correctness. Shared
compromise can make two builders reproduce the same malicious verifier. Likewise a
runtime that measures artifact A and executes artifact B defeats the current provenance
chain.

## NEXT

1. Bind builder identities to independently attested build environments.
2. Add signed compiler/toolchain provenance.
3. Close measure-A/execute-B with immutable load-handle identity or equivalent native custody.
4. Add revocation and epoch-scoped trust policy for builders/toolchains/artifacts/ABIs.
5. Run canonical full validation before merge.
