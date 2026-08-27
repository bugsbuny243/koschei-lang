# KOSCHEI VERIFIER BUILD PROVENANCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / VERIFIED-IR BUILD-INPUT IDENTITY / NOT YET REPRODUCIBLE-BUILD PROOF

## PURPOSE

A provider adapter ABI that merely contains a caller-supplied verifier implementation
digest is insufficient. Koschei must bind that digest to the exact verifier artifact
that was built and the exact verifier artifact that the runtime admitted before raw
provider responses are interpreted.

The build-input identity must also not be caller-selected metadata. V1 now derives it
from Koschei's existing sealed native semantic/proof chain rather than inventing a
parallel IR format.

V1 sanctioned chain:

`NativeSigilMir`
`-> NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> toolchain digest`
`-> verifier artifact bytes`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1(verifier_implementation_digest)`
`-> runtime measures loaded artifact bytes`
`-> VerifierRuntimeAdmissionV1`
`-> ProviderNativeVerificationReceiptV1`
`-> finality provenance`

## VERIFIED IR BUILD INPUT

`VerifiedIrBuildInputV1` is not a second compiler IR. It is a non-authoritative identity
receipt derived from the existing sealed native compiler/proof world:

- `NativeSigilMir.fingerprint`,
- Universe plan digest,
- `NativeSigilProofBundle.digest`,
- Library proof digest,
- proof decision,
- authority=false.

`derive_verified_ir_build_input_v1(...)` first re-verifies the native MIR/proof chain and
then derives the deterministic `build_input_digest`.

The sanctioned build API is:

`attest_verifier_build_from_verified_ir_v1(...)`

It does not accept a free caller-selected `build_input_digest`. The provenance object
inherits that digest from the sealed `VerifiedIrBuildInputV1` object.

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
- verified-IR-derived build-input digest,
- toolchain digest,
- build profile,
- authority=false.

It is HMAC-SHA256 authenticated with a dedicated `build_provenance_key`.

`assert_from_verified_ir(...)` additionally re-verifies the supplied sealed native MIR
and proof identity and requires the provenance build-input digest to equal that exact
verified-input digest.

This V1 still does NOT prove that the artifact was deterministically derived from the
verified IR or that the toolchain itself is trustworthy.

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

- caller injection of an arbitrary build-input digest on the sanctioned build path,
- moving build provenance to a different sealed MIR/proof identity,
- ABI manifest claiming one verifier digest while different artifact bytes are loaded,
- replacing verifier artifact bytes after build provenance issuance,
- changing toolchain/profile metadata without build provenance key,
- changing runtime admission artifact or ABI binding without admission key,
- executing provider-native verification through the sanctioned path before artifact admission,
- dropping build/admission provenance from the final provider-finality envelope.

## DOES NOT PROTECT AGAINST

- malicious verifier semantics that successfully pass the current native proof policy,
- compromised build-provenance or runtime-admission keys,
- a compromised builder/toolchain producing malicious output for a valid verified input,
- non-reproducible builds,
- compromised toolchain provenance,
- TOCTOU if production runtime measures one artifact but executes different bytes afterward,
- host compromise, debugger/memory attacks, or hardware faults,
- provider-native verifier logic errors.

## ASSUMPTIONS

- `NativeSigilMir` and `NativeSigilProofBundle` remain sealed and fail-closed,
- artifact bytes measured by runtime are exactly the bytes executed,
- artifact measurement occurs before verifier callback invocation,
- build and runtime admission keys are protected and separated,
- adapter ABI admission is fail-closed,
- production implementation prevents artifact substitution after admission.

## FAILURE MODE

If runtime measures artifact A but executes artifact B, provenance becomes false. V1
therefore requires production loading to make measurement and execution identity the
same trust boundary.

If a valid verified IR input can still semantically describe a malicious verifier, this
layer will faithfully bind the malicious artifact to that verified input. Verification
of identity is not proof of benign intent.

If the builder/toolchain is compromised, it can produce a malicious artifact while the
verified input remains legitimate. V1 therefore still needs independent rebuild and
compiler/toolchain provenance.

## NEXT

1. Add independent reproducible-build verification: two isolated builders must produce
   the same verifier artifact digest from the same `VerifiedIrBuildInputV1`.
2. Bind toolchain digest to signed compiler/toolchain provenance.
3. Add runtime load-handle identity so measurement and execution cannot diverge.
4. Add revocation/admission policy for compromised verifier artifacts.
5. Extend source-intent provenance if a stronger source-to-MIR commitment is needed.
