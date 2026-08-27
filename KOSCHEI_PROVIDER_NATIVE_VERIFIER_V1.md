# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / ADAPTER ABI IDENTITY WIRED / PROVIDER NETWORK ADAPTER REMAINS EXTERNAL

## PURPOSE

`effect-completed` is local. Provider finality must be derived from raw provider bytes
through a known verifier contract, not from caller-selected state/reference/proof.

Sanctioned path:

`local effect result bytes`
`-> sealed ProviderAdapterAbiV1`
`-> raw provider response bytes`
`-> trusted provider-native verifier`
`-> ProviderNativeVerificationReceiptV1`
`-> receipt-bound provider verdict`
`-> finality attestation`
`-> ExternalFinalityProofEnvelopeV1`

## PROVIDER ADAPTER ABI

`ProviderAdapterAbiV1` identifies the verifier contract by binding:

- provider id,
- adapter id,
- schema id,
- schema version,
- verifier implementation digest,
- authority=false.

The ABI digest is deterministic provenance, not authority and not a code signature.
Production must derive the verifier implementation digest from a reproducible/attested
artifact rather than accepting an arbitrary label from application code.

## NATIVE VERIFICATION RECEIPT

The receipt now binds the adapter ABI digest and verifier implementation digest in
addition to the exact effect envelope, effect receipt/measurement, raw response,
expected/verified external reference, provider proof, epoch and state.

A receipt produced under schema/version/verifier A cannot validate under ABI B.

## V1 REFERENCE CONTRACT

The complete successful effect callback bytes are the canonical expected external
reference. For Pi payment V1 these bytes are the canonical txid bytes. Provider-native
verification must return the same canonical reference or fail before verdict issuance.

No unverified Pi JSON schema is hard-coded in Lang core.

## TRUST-ROLE SEPARATION

- decision_key: authorization bridge
- runtime_key: permit/consumption
- effect_key: local effect measurement
- provider_native_verifier_key: ABI-bound raw-response verification receipt
- provider_verifier_key: provider finality verdict
- finality_key: Koschei finality attestation

## PROTECTS AGAINST

- caller-selected provider finality state/reference/proof after native verification,
- raw provider response rebinding,
- provider response referencing a different external object than the measured effect,
- presenting one native receipt under another provider/schema/schema-version ABI,
- relabeling which verifier implementation produced a receipt,
- dropping ABI/verifier identity from the end-to-end finality envelope.

## DOES NOT PROTECT AGAINST

- malicious/buggy verifier implementation whose digest is nevertheless trusted,
- false implementation digests supplied by a compromised build/attestation authority,
- compromised verifier/finality/runtime keys,
- unauthenticated provider transport accepted by the verifier,
- provider reorg/reversal after its own finality semantics,
- host/runtime compromise or replay-state rollback.

## ASSUMPTIONS

- ABI admission is controlled by trusted runtime policy,
- verifier implementation digest corresponds to the code actually executed in production,
- provider schema/version identity is pinned and reviewed,
- provider-native verifier performs real authenticated provider verification,
- final consumers validate the full ExternalFinalityProofEnvelopeV1.

## FAILURE MODE

ABI identity becomes decorative if application code can register arbitrary implementation
digests as trusted. It becomes false provenance if the digest does not correspond to the
executed verifier binary/module. Therefore production must bind ABI admission to build
provenance/attestation.

A valid receipt proves which admitted ABI/verifier identity was used and which raw response
was measured; it cannot repair a verifier that accepts false provider data.

## NEXT

1. Bind `verifier_implementation_digest` to Koschei build-artifact provenance instead of a caller-provided digest.
2. Define runtime adapter admission policy and revocation/epoch rules.
3. Pin an exact supported Pi backend/payment schema before implementing a production parser.
4. Move raw-response receipt storage and replay/audit state into durable runtime custody.
