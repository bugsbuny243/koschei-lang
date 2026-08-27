# KOSCHEI VERIFIER REPRODUCIBLE BUILD V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / TWO-BUILDER REPRODUCIBILITY GATE / PROVIDER PATH WIRED

## PURPOSE

One authenticated builder is not enough to establish reproducible derivation. V1
requires two distinct authenticated builder identities to bind the same
`VerifiedIrBuildInputV1` and independently report the same exact verifier artifact
digest before a reproducibility receipt may be sealed.

Sanctioned chain:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> builder A observation`
`-> builder B observation`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1`
`-> base VerifierRuntimeAdmissionV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> ProviderNativeVerificationReceiptV1`
`-> provider verdict / finality provenance`

## BUILDER OBSERVATION

Each `VerifierBuilderObservationV1` binds:

- distinct builder identity,
- exact verified-input digest,
- toolchain digest,
- build profile,
- exact artifact digest,
- authority=false.

Each observation is authenticated under its own builder key.

## REPRODUCIBILITY RECEIPT

A receipt is issued only when:

1. both builder observations authenticate,
2. builder identities are different,
3. both bind the same `VerifiedIrBuildInputV1`,
4. both bind the same exact verifier artifact digest.

The receipt is authenticated under a separate `reproducibility_key` and carries no
authority.

## RUNTIME GATE

`VerifierReproducibleRuntimeAdmissionV1` layers over exact-artifact runtime admission.
Minting the gate verifies the full two-builder reproducibility receipt, verified-IR-bound
build provenance, ABI binding, and exact runtime artifact measurement.

Provider-native verification now requires this gate. The base
`VerifierRuntimeAdmissionV1` is not sufficient by itself for the sanctioned provider
verification path.

`ProviderNativeVerificationReceiptV1` binds both:

- reproducibility receipt digest,
- reproducible runtime-admission digest.

`ExternalFinalityProofEnvelopeV1` carries the same digests so finality provenance cannot
drop the reproducibility gate after provider verification.

## PROTECTS AGAINST

- one builder unilaterally declaring a reproducible verifier artifact,
- counting one builder identity twice,
- two builders producing different artifact bytes while claiming reproducibility,
- rebinding the reproducibility receipt to another verified input or artifact,
- altering the reproducibility/runtime-admission link without the gate key,
- running the sanctioned provider-native verifier with only base runtime admission,
- dropping reproducibility provenance from provider finality proof.

## DOES NOT PROTECT AGAINST

- two colluding or identically compromised builders,
- both builders using the same compromised toolchain and producing the same malicious artifact,
- false toolchain identity/provenance,
- non-independent build environments despite distinct logical builder ids,
- measure-A/execute-B runtime TOCTOU,
- host/runtime or protected-key compromise.

## ASSUMPTIONS

- builder identities correspond to independently controlled build authorities in production,
- builder keys and reproducibility/gate keys are separately protected,
- `VerifiedIrBuildInputV1` validation remains fail-closed,
- artifact measurement is canonical and stable,
- runtime executes the exact admitted bytes,
- provider-native callers cannot bypass the reproducibility-gated API with an exposed lower primitive.

## FAILURE MODE

Reproducibility proves agreement, not correctness. Two compromised builders can agree on
the same malicious artifact. If both builders share the same compromised toolchain, the
receipt can still be reproducible while semantically unsafe.

If production exposes an alternate provider-native verification path that accepts only
`VerifierRuntimeAdmissionV1`, the gate can be bypassed even though the sanctioned Python
prototype is wired correctly.

## NEXT

1. Bind builder identities to independently attested build environments.
2. Add signed compiler/toolchain provenance.
3. Add immutable runtime load-handle identity to close measure-A/execute-B TOCTOU.
4. Add revocation/epoch policy for builder, toolchain, artifact and adapter trust.
5. Produce canonical validation receipts before merge.
