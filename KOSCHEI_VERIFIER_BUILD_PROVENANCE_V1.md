# KOSCHEI VERIFIER BUILD PROVENANCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / ARTIFACT IDENTITY AND RUNTIME ADMISSION / NOT YET REPRODUCIBLE-BUILD PROOF

## PURPOSE

A provider adapter ABI that merely contains a caller-supplied verifier implementation
digest is insufficient. Koschei must bind that digest to the exact verifier artifact
that was built and the exact verifier artifact that the runtime admitted before raw
provider responses are interpreted.

V1 sanctioned chain:

`build input digest`
`-> toolchain digest`
`-> verifier artifact bytes`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1(verifier_implementation_digest)`
`-> runtime measures loaded artifact bytes`
`-> VerifierRuntimeAdmissionV1`
`-> ProviderNativeVerificationReceiptV1`
`-> finality provenance`

## ARTIFACT MEASUREMENT

`measure_verifier_artifact_v1(bytes)` uses domain-separated SHA-256 over the exact
artifact byte string.

The same artifact digest must appear in:

- authenticated build provenance,
- `ProviderAdapterAbiV1.verifier_implementation_digest`,
- authenticated runtime admission.

Any mismatch is rejected before the provider-native verifier callback is invoked.

## BUILD PROVENANCE

`VerifierBuildProvenanceV1` binds:

- verifier artifact digest,
- build-input digest,
- toolchain digest,
- build profile,
- authority=false.

It is HMAC-SHA256 authenticated with a dedicated `build_provenance_key`.

This V1 proves which metadata was authenticated for one exact artifact. It does NOT yet
prove that the artifact was deterministically derived from the declared build input or
that the toolchain itself is trustworthy.

## RUNTIME ADMISSION

`VerifierRuntimeAdmissionV1` re-measures exact loaded artifact bytes and requires:

1. build provenance authentication succeeds,
2. loaded artifact digest equals build-provenance artifact digest,
3. loaded artifact digest equals adapter ABI verifier implementation digest,
4. adapter ABI seal verifies,
5. runtime admission is authenticated with a separate `runtime_admission_key`.

The provider-native verifier callback is invoked only after this admission verifies.

## TRUST-ROLE SEPARATION

- `build_provenance_key`: authenticates build artifact metadata.
- `runtime_admission_key`: authenticates runtime load/admission observation.
- `provider_native_verifier_key`: authenticates provider-native verification result.

These roles are intentionally separate.

## PROTECTS AGAINST

- ABI manifest claiming one verifier digest while different artifact bytes are loaded,
- replacing verifier artifact bytes after build provenance issuance,
- changing build-input/toolchain/profile metadata without build provenance key,
- changing runtime admission artifact or ABI binding without admission key,
- executing provider-native verification through the sanctioned path before artifact admission,
- dropping build/admission provenance from the final provider-finality envelope.

## DOES NOT PROTECT AGAINST

- malicious verifier source that was intentionally built and admitted,
- compromised build-provenance or runtime-admission keys,
- a compromised builder lying about build-input/toolchain digests,
- non-reproducible builds,
- compromised toolchain producing malicious output,
- TOCTOU if production runtime measures one artifact but executes different bytes afterward,
- host compromise, debugger/memory attacks, or hardware faults,
- provider-native verifier logic errors.

## ASSUMPTIONS

- artifact bytes measured by runtime are exactly the bytes executed,
- artifact measurement occurs before verifier callback invocation,
- build and runtime admission keys are protected and separated,
- adapter ABI admission is fail-closed,
- production implementation prevents artifact substitution after admission.

## FAILURE MODE

If runtime measures artifact A but executes artifact B, provenance becomes false. V1
therefore requires production loading to make measurement and execution identity the
same trust boundary.

If build provenance says source/IR X produced artifact A without independently proving
that derivation, the receipt proves only the authenticated claim and exact artifact
identity, not the derivation itself.

## NEXT

1. Bind `build_input_digest` to canonical Koschei Verified IR / source-intent provenance.
2. Add reproducible-build verification using an independent rebuild receipt.
3. Bind toolchain digest to signed compiler/toolchain provenance.
4. Add runtime load-handle identity so measurement and execution cannot diverge.
5. Add revocation/admission policy for compromised verifier artifacts.
