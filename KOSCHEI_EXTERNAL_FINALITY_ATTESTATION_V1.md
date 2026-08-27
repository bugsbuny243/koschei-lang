# KOSCHEI EXTERNAL FINALITY ATTESTATION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / RAW RESPONSE + ADAPTER ABI PROVENANCE WIRED

## PURPOSE

Local `effect-completed` is not remote finality. The external-finality chain now requires
provider-native verification of exact raw response bytes under a sealed provider adapter ABI.

`EffectExecutionProofEnvelopeV1`
`-> ProviderAdapterAbiV1`
`-> raw provider response`
`-> ProviderNativeVerificationReceiptV1`
`-> ExternalProviderFinalityVerdictV1`
`-> ExternalFinalityAttestationV1`
`-> ExternalFinalityProofEnvelopeV1`

## SEMANTIC STATES

Provider-native/finality states remain `pending`, `finalized`, or `rejected`; end-to-end
terminal states are `provider-pending`, `provider-finalized`, or `provider-rejected`.

## IDENTITY AND TRUST ROLES

Provider verifier provenance is no longer anonymous. The native receipt and final proof bind:
provider id, adapter ABI digest, schema/version identity, verifier implementation digest,
raw response digest, verified reference, provider proof, state, and observation epoch.

The verifier implementation digest is provenance only. Production must obtain it from the
actual build/artifact measurement; accepting arbitrary application labels would defeat the
claim.

## AUTHORITY RULE

Provider responses, ABI manifests, verifier receipts, verdicts, attestations and proof
envelopes all carry `authority=false`. External truth never becomes ambient Koschei authority.

## PROTECTS AGAINST

- treating local callback completion as provider finality,
- caller-selected provider state/reference/proof after native verification,
- raw response rebinding,
- cross-schema/cross-verifier receipt relabeling,
- dropping verifier identity from full finality provenance.

## DOES NOT PROTECT AGAINST

- a trusted but buggy/malicious verifier,
- a false implementation digest admitted by compromised build provenance,
- provider reorg/reversal,
- compromised trust-role keys, host/runtime, or replay state,
- Pi/provider network correctness outside the verifier boundary.

## ASSUMPTIONS

- adapter ABI admission is trusted and fail-closed,
- verifier implementation measurement corresponds to the executed code,
- provider-native transport/proof verification is correct,
- the full finality envelope is the authoritative provenance surface.

## FAILURE MODE

If the implementation digest is not bound to the code that actually executed, ABI identity
is false provenance. If the verifier lies, Koschei can prove which verifier identity and raw
response were used but cannot manufacture external truth.

## NEXT

Bind verifier implementation identity to Koschei build-artifact provenance and runtime adapter
admission/revocation. Then pin an exact Pi payment/backend schema before production parsing.
