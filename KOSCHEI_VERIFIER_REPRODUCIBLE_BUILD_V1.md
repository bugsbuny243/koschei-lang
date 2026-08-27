# KOSCHEI VERIFIER REPRODUCIBLE BUILD V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / TWO-BUILDER + SIGNED-TOOLCHAIN REPRODUCIBILITY GATE / PROVIDER PATH WIRED

## PURPOSE

One authenticated builder is not enough. V1 requires two distinct authenticated builder
identities to bind the same `VerifiedIrBuildInputV1`, authenticated toolchain provenance,
and the same exact verifier artifact digest before provider verification can proceed.

Sanctioned chain:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> ToolchainProvenanceV1`
`-> builder A observation`
`-> ToolchainProvenanceV1`
`-> builder B observation`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1`
`-> VerifierRuntimeAdmissionV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> ProviderNativeVerificationReceiptV1`
`-> provider verdict / finality provenance`

## BUILDER OBSERVATION

Each builder observation binds:

- distinct builder identity,
- exact verified-input digest,
- authenticated toolchain provenance digest,
- build profile,
- exact verifier artifact digest,
- authority=false.

The sanctioned observation API does not accept a caller-selected `toolchain_digest`.

## REPRODUCIBILITY RECEIPT

The receipt records the exact toolchain provenance digest used by builder A and builder B.
The two toolchains may differ, but both builders must still produce the same verifier
artifact digest.

## BUILD PROVENANCE CROSS-CHECK

The signed toolchain bound by `VerifierBuildProvenanceV1` must appear in at least one of
the two authenticated builder observations before reproducible runtime admission is minted.
This prevents a separate unobserved toolchain identity from being introduced only at the
build-provenance layer.

## RUNTIME GATE

Provider-native verification requires `VerifierReproducibleRuntimeAdmissionV1`; base
runtime admission alone is insufficient. Native verification and finality provenance carry
the reproducibility receipt/gate identities.

## PROTECTS AGAINST

- one builder unilaterally declaring reproducibility,
- counting one builder identity twice,
- differing artifacts being admitted as reproducible,
- arbitrary caller-selected toolchain digests on sanctioned builder/build APIs,
- relabeling builder evidence under another signed toolchain,
- using a build-provenance toolchain absent from both builder observations,
- dropping reproducibility provenance from provider finality proof.

## DOES NOT PROTECT AGAINST

- two colluding or identically compromised builders,
- intentionally signed malicious toolchains,
- compromised toolchain signing authority,
- two different signed toolchains sharing the same malicious defect,
- non-independent builder environments despite distinct logical ids,
- measure-A/execute-B runtime TOCTOU,
- host/runtime or protected-key compromise.

## ASSUMPTIONS

- builder identities map to independently controlled build authorities in production,
- toolchain signing authorities are protected,
- signed toolchain artifact bytes are the actual bytes used by builders,
- runtime executes the exact admitted verifier bytes,
- lower verification primitives are not exposed as bypass paths.

## FAILURE MODE

Reproducibility proves agreement, not correctness. Signed provenance proves toolchain
identity, not compiler correctness. Two compromised builders or two signed toolchains with
the same defect can still agree on malicious output.

## NEXT

1. Bind builder identities to independently attested build environments.
2. Add epoch/revocation policy for toolchains/builders/artifacts/ABIs.
3. Add immutable runtime load-handle identity to close measure-A/execute-B TOCTOU.
4. Explore diverse-compiler/self-rebuild verification for compiler correctness evidence.
5. Produce canonical validation receipts before merge.
