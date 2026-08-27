# KOSCHEI VERIFIER BUILD PROVENANCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / VERIFIED-IR BUILD INPUT + ARTIFACT IDENTITY / REPRODUCIBILITY GATE ADDED

## PURPOSE

A provider adapter ABI that merely contains a caller-supplied verifier implementation
digest is insufficient. Koschei binds that digest to the exact verifier artifact,
its sealed native semantic/proof build input, and the exact artifact admitted by the
runtime.

The sanctioned build-input identity is derived from existing Koschei structures:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> verifier artifact build provenance`

The sanctioned build attestation no longer accepts a caller-selected
`build_input_digest`.

## VERIFIED IR BUILD INPUT

`VerifiedIrBuildInputV1` binds:

- sealed native MIR fingerprint,
- Universe plan digest,
- native proof digest,
- Library proof digest,
- proof decision,
- authority=false.

`VerifierBuildProvenanceV1.assert_from_verified_ir(...)` rechecks that the artifact
provenance derives from this exact semantic/proof identity.

## ARTIFACT MEASUREMENT

`measure_verifier_artifact_v1(bytes)` uses domain-separated SHA-256 over exact artifact
bytes. The same digest must be present in build provenance, adapter ABI implementation
identity, and runtime admission.

## REPRODUCIBLE BUILD EXTENSION

`KOSCHEI_VERIFIER_REPRODUCIBLE_BUILD_V1.md` adds two independent authenticated builder
observations over the same `VerifiedIrBuildInputV1`. Both must report the same exact
artifact digest before `VerifierReproducibleBuildReceiptV1` can be sealed.

A higher `VerifierReproducibleRuntimeAdmissionV1` then layers that receipt over the
existing exact-artifact runtime admission.

The provider-native verifier boundary has NOT yet been switched to require the higher
gate in this checkpoint, so reproducibility must not yet be marketed as end-to-end
provider-finality enforcement.

## PROTECTS AGAINST

- caller injection of arbitrary verifier build-input digest on the sanctioned path,
- rebinding build provenance to another sealed MIR/proof world,
- ABI claiming one verifier while different bytes are loaded,
- artifact or build metadata tampering under stated key assumptions,
- one builder alone declaring reproducibility once the higher gate is used,
- two independent builder observations silently disagreeing on artifact bytes.

## DOES NOT PROTECT AGAINST

- malicious verifier semantics accepted by current native policy,
- compromised builder/toolchain output,
- two colluding or identically compromised builders,
- false toolchain provenance,
- measure-A/execute-B runtime TOCTOU,
- host/runtime or protected-key compromise.

## ASSUMPTIONS

- NativeSigilMir and NativeSigilProofBundle validation remains fail-closed,
- builder and runtime trust-role keys are separately protected,
- runtime measures exactly the bytes later executed,
- production builder identities map to genuinely independent build authorities.

## FAILURE MODE

Verified semantic input plus reproducibility proves identity and agreement, not semantic
correctness of the resulting artifact. Two compromised builders can still agree on the
same malicious output. A shared compromised toolchain can also produce reproducible but
unsafe artifacts.

## NEXT

1. Require `VerifierReproducibleRuntimeAdmissionV1` at provider-native verification.
2. Carry reproducibility proof and gate digests into final finality provenance.
3. Bind toolchain digest to signed compiler/toolchain provenance.
4. Bind builder identities to independently attested build environments.
5. Close runtime measure-A/execute-B TOCTOU with one immutable load handle.
