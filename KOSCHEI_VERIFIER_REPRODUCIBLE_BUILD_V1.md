# KOSCHEI VERIFIER REPRODUCIBLE BUILD V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / TWO-BUILDER + SIGNED-TOOLCHAIN + ATTESTED-ENVIRONMENT GATE / PROVIDER PATH WIRED

## PURPOSE

One authenticated builder is not enough. V1 requires two distinct authenticated builder
identities to bind the same `VerifiedIrBuildInputV1`, authenticated toolchain provenance,
distinct authenticated builder environments, and the same exact verifier artifact digest
before provider verification can proceed.

Sanctioned chain:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> ToolchainProvenanceV1 + BuilderEnvironmentAttestationV1`
`-> builder A observation`
`-> ToolchainProvenanceV1 + BuilderEnvironmentAttestationV1`
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
- authenticated builder-environment attestation digest,
- build profile,
- exact verifier artifact digest,
- authority=false.

## ENVIRONMENT INDEPENDENCE

Builder A and B must differ in both `environment_id` and measured environment digest.
Changing only a logical builder label is insufficient. Reusing the same measured
environment under a second id is rejected before a reproducibility receipt is minted.

The bootstrap environment attestation uses authenticated environment/workload measurements.
It is not yet hardware-backed remote attestation.

## REPRODUCIBILITY RECEIPT

The receipt records the exact toolchain provenance and environment-attestation digests
used by builder A and B. Toolchains may differ, but the final verifier artifact digest
must be identical.

## BUILD PROVENANCE CROSS-CHECK

The signed toolchain bound by `VerifierBuildProvenanceV1` must appear in at least one of
the authenticated builder observations before reproducible runtime admission is minted.

## RUNTIME GATE

Provider-native verification requires `VerifierReproducibleRuntimeAdmissionV1`; base
runtime admission alone is insufficient. Minting the gate now verifies the two-builder
receipt including its signed toolchains and distinct attested environments.

## PROTECTS AGAINST

- one builder unilaterally declaring reproducibility,
- counting one builder identity twice,
- counting one measured environment twice under different builder labels,
- differing artifacts being admitted as reproducible,
- arbitrary caller-selected toolchain digests on sanctioned paths,
- relabeling builder evidence under another signed toolchain/environment,
- dropping reproducibility provenance from provider finality proof.

## DOES NOT PROTECT AGAINST

- two colluding builders in distinct but attacker-controlled environments,
- compromised environment-attestation authority,
- shared host/hypervisor compromise,
- intentionally signed malicious toolchains,
- compromised toolchain signing authority,
- common-mode compiler defects,
- measure-A/execute-B runtime TOCTOU,
- host/runtime or protected-key compromise.

## ASSUMPTIONS

- environment ids and measurements map to genuinely isolated build environments in production,
- attestation and toolchain signing authorities are protected,
- measured workload/environment data is canonical,
- runtime executes the exact admitted verifier bytes,
- lower verification primitives are not exposed as bypass paths.

## FAILURE MODE

Reproducibility proves agreement, not correctness. Environment attestation proves the
identity Koschei authenticated, not hardware isolation. A compromised attestation
authority can falsely mint two apparently independent environments.

## NEXT

1. Add provider-neutral TPM/TEE/cloud remote-attestation evidence interface.
2. Add epoch/revocation policy for environments/toolchains/builders/artifacts/ABIs.
3. Add immutable runtime load-handle identity to close measure-A/execute-B TOCTOU.
4. Explore diverse-compiler/self-rebuild verification.
5. Produce canonical validation receipts before merge.
