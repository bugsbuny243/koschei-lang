# KOSCHEI TOOLCHAIN PROVENANCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / AUTHENTICATED TOOLCHAIN IDENTITY / NOT YET TOOLCHAIN CORRECTNESS PROOF

## PURPOSE

Builder observations and verifier build provenance must not accept arbitrary caller-selected
`toolchain_digest` values. V1 binds one exact compiler/toolchain artifact byte string to
authenticated identity metadata and requires sanctioned verifier-build paths to inherit that
identity.

## OBJECT

`ToolchainProvenanceV1` binds:

- toolchain id,
- toolchain version,
- exact toolchain artifact digest,
- build profile,
- authority=false,
- authenticated provenance digest.

`measure_toolchain_artifact_v1(bytes)` uses domain-separated SHA-256 over exact toolchain
artifact bytes.

`attest_toolchain_provenance_v1(...)` authenticates the resulting identity with a dedicated
`toolchain_signing_key`.

## SANCTIONED VERIFIER BUILD PATH

`VerifierBuildProvenanceV1` no longer receives a caller-selected toolchain digest on its
sanctioned API. `attest_verifier_build_from_verified_ir_v1(...)` requires one authenticated
`ToolchainProvenanceV1` and inherits `toolchain.provenance_digest`.

`VerifierBuilderObservationV1` likewise requires an authenticated toolchain receipt and binds
its provenance digest into the builder observation.

`VerifierReproducibleBuildReceiptV1` carries the exact toolchain provenance digest used by
each builder. Builders may use different authenticated toolchains, but both must still
produce the same verifier artifact digest.

`VerifierReproducibleRuntimeAdmissionV1` additionally requires that the toolchain bound by
`VerifierBuildProvenanceV1` appears in at least one authenticated builder observation.

## PROTECTS AGAINST

- caller injection of arbitrary toolchain digest on sanctioned verifier build APIs,
- relabeling a builder observation under another toolchain receipt,
- toolchain artifact substitution after provenance issuance,
- changing toolchain version/profile/artifact identity without the signing key,
- build provenance referring to a toolchain absent from the reproducible builder evidence.

## DOES NOT PROTECT AGAINST

- a malicious compiler/toolchain that is intentionally signed,
- compromise of the toolchain signing key,
- a signing authority falsely approving a malicious toolchain artifact,
- compiler miscompilation or semantic bugs,
- two different authenticated toolchains that share the same malicious defect,
- host/runtime compromise or measure-A/execute-B TOCTOU.

## ASSUMPTIONS

- toolchain signing keys are protected and separated from builder/reproducibility/runtime keys,
- signed artifact bytes are the actual compiler/toolchain bytes used by the builder,
- builder environments do not substitute a different compiler after verification,
- production policy controls which toolchain identities/versions are trusted or revoked.

## FAILURE MODE

A signed malicious compiler remains malicious. This receipt authenticates identity and
artifact provenance, not semantic correctness. If the signing authority is compromised or
approves a malicious compiler, all downstream reproducibility receipts may still agree on
malicious output.

## NEXT

1. Add toolchain trust policy with epochs, revocation and minimum accepted versions.
2. Bind toolchain identity to independently attested builder environments.
3. Add compiler self-host/rebuild or diverse-compiler verification where practical.
4. Add immutable runtime load handles to close measure-A/execute-B TOCTOU.
