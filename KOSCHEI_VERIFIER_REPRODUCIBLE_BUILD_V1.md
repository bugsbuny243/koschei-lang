# KOSCHEI VERIFIER REPRODUCIBLE BUILD V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / TWO-BUILDER REPRODUCIBILITY GATE / PROVIDER BRIDGE NOT YET SWITCHED

## PURPOSE

One authenticated builder is not enough to establish reproducible derivation. V1
requires two distinct authenticated builder identities to bind the same
`VerifiedIrBuildInputV1` and independently report the same exact verifier artifact
digest before a reproducibility receipt may be sealed.

Sanctioned chain in this slice:

`NativeSigilMir + NativeSigilProofBundle`
`-> VerifiedIrBuildInputV1`
`-> builder A observation`
`-> builder B observation`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierBuildProvenanceV1`
`-> ProviderAdapterAbiV1`
`-> base VerifierRuntimeAdmissionV1`
`-> VerifierReproducibleRuntimeAdmissionV1`

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

`VerifierReproducibleRuntimeAdmissionV1` layers over the existing runtime artifact
admission. Minting the gate first verifies the full two-builder reproducibility receipt,
then verifies build provenance and exact runtime artifact admission.

Downstream consumers may authenticate the compact gate under a dedicated
`reproducible_admission_key` and bind it to the exact base runtime admission and ABI.

## PROTECTS AGAINST

- one builder unilaterally declaring a reproducible verifier artifact,
- counting one builder identity twice,
- two builders producing different artifact bytes while claiming reproducibility,
- rebinding the reproducibility receipt to another verified input or artifact,
- altering the reproducibility/runtime-admission link without the gate key.

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
- runtime executes the exact admitted bytes.

## FAILURE MODE

Reproducibility proves agreement, not correctness. Two compromised builders can agree on
the same malicious artifact. If both builders share the same compromised toolchain, the
receipt can still be reproducible while semantically unsafe.

The current bootstrap provider-native verification path still consumes the older base
`VerifierRuntimeAdmissionV1`. Therefore this slice must NOT yet be described as
production-enforced reproducibility for provider finality. The next patch is to require
`VerifierReproducibleRuntimeAdmissionV1` at the provider-native verifier boundary and
carry its digest into finality provenance.

## NEXT

1. Switch provider-native verification to require the reproducibility-gated admission.
2. Carry reproducibility receipt/gate digests into the final finality envelope.
3. Bind builder identities to independent build environments/attestation.
4. Add signed toolchain provenance.
5. Add immutable load-handle identity to close measure-A/execute-B TOCTOU.
