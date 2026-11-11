# KOSCHEI VERIFIER BUILD PROVENANCE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / VERIFIED-IR + SIGNED-TOOLCHAIN BUILD INPUT / REPRODUCIBILITY GATE WIRED

## PURPOSE

Verifier build provenance must not accept caller-selected semantic input or toolchain
identity. The sanctioned path derives its build input from existing sealed Koschei native
IR/proof structures and derives its toolchain identity from authenticated
`ToolchainProvenanceV1`.

Sanctioned chain:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> ToolchainProvenanceV1`
`-> verifier artifact bytes`
`-> VerifierBuildProvenanceV1`
`-> reproducible builder evidence`
`-> ProviderAdapterAbiV1`
`-> runtime admission`

## VERIFIED IR INPUT

`VerifiedIrBuildInputV1` binds MIR fingerprint, Universe plan, native proof, Library proof
and proof decision. The sanctioned build API cannot choose `build_input_digest` directly.

## SIGNED TOOLCHAIN INPUT

`attest_verifier_build_from_verified_ir_v1(...)` now requires:

- authenticated `ToolchainProvenanceV1`,
- exact toolchain artifact bytes,
- toolchain signing key verification,
- build profile,
- exact verifier artifact bytes.

The resulting `VerifierBuildProvenanceV1.toolchain_digest` is the authenticated toolchain
provenance digest, not a caller-selected label.

`assert_from_verified_ir(...)` revalidates both the verified semantic input and signed
toolchain identity before accepting the build provenance binding.

## ARTIFACT MEASUREMENT

Verifier artifact measurement remains domain-separated SHA-256 over exact bytes. The same
artifact identity must match build provenance, provider adapter ABI and runtime admission.

## REPRODUCIBILITY

Two independently authenticated builder observations bind their own signed toolchain
provenance. Their exact toolchain provenance digests are carried into
`VerifierReproducibleBuildReceiptV1`.

The toolchain used by `VerifierBuildProvenanceV1` must appear in at least one builder
observation before reproducible runtime admission can be minted.

## PROTECTS AGAINST

- caller-selected build-input digest,
- caller-selected toolchain digest on sanctioned build path,
- build provenance relabeling under another signed toolchain,
- verifier artifact substitution after provenance issuance,
- introducing a build-provenance toolchain absent from reproducible builder evidence,
- dropping artifact/reproducibility identity before provider finality verification.

## DOES NOT PROTECT AGAINST

- a malicious toolchain intentionally signed by trusted authority,
- compromised signing/build/runtime keys,
- compiler semantic bugs or miscompilation,
- colluding builders or common-mode toolchain defects,
- measure-A/execute-B runtime TOCTOU,
- host/runtime compromise.

## ASSUMPTIONS

- toolchain signing authority is protected,
- signed toolchain bytes are the bytes actually used to build,
- verified IR/proof validation remains fail-closed,
- runtime executes the exact admitted verifier artifact.

## FAILURE MODE

Signed provenance authenticates identity, not correctness. A malicious compiler that is
legitimately signed can still produce reproducible malicious output. Common-mode compiler
defects can survive independent builds.

## NEXT

1. Bind builder identities to independently attested build environments.
2. Add epoch/revocation policy for toolchain and builder trust.
3. Close measure-A/execute-B TOCTOU with immutable load handles.
4. Explore diverse compiler/self-rebuild verification for stronger compiler correctness evidence.
5. Produce canonical validation receipts before merge.
