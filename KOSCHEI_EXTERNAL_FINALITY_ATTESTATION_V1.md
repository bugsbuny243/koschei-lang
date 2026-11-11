# KOSCHEI EXTERNAL FINALITY ATTESTATION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / RAW RESPONSE + REPRODUCIBLE VERIFIER + TRUST-GENERATION PROVENANCE WIRED

## PURPOSE

Local `effect-completed` is not remote finality. The external-finality chain requires provider-native verification of exact raw response bytes under an admitted reproducible verifier artifact and carries the builder trust-generation identities that governed that verifier.

`EffectExecutionProofEnvelopeV1`
`-> ProviderAdapterAbiV1`
`-> reproducible verifier admission`
`-> current builder trust-generation guard`
`-> raw provider response`
`-> ProviderNativeVerificationReceiptV1`
`-> ExternalProviderFinalityVerdictV1`
`-> ExternalFinalityAttestationV1`
`-> ExternalFinalityProofEnvelopeV1`

## SEMANTIC STATES

Provider-native/finality states remain `pending`, `finalized`, or `rejected`; end-to-end terminal states are `provider-pending`, `provider-finalized`, or `provider-rejected`.

## TRUST-GENERATION PROVENANCE

The provider-native receipt binds builder A/B trust-anchor ids, generations and manifest digests from the authenticated reproducibility receipt. New provider verification is rejected before callback execution if either generation is no longer current under the supplied authoritative generation state/store.

## VALIDATION MODES

Two questions are now separate:

- `assert_external_finality_historical_integrity_v1(...)`: verifies the sealed lineage as issued without asking whether its trust generations are still current today.
- `ExternalFinalityProofEnvelopeV1.assert_valid(...)`: current operational validation; it additionally requires builder A/B trust generations to remain current.

A generation advance can therefore invalidate current operational use without rewriting the historical fact that an older proof was authentically sealed.

Historical integrity does not grant authority for a new execution.

See `KOSCHEI_FINALITY_VALIDATION_MODES_V1.md`.

## IDENTITY AND TRUST ROLES

The native receipt and final proof bind provider id, adapter ABI digest, verifier implementation digest, reproducibility/runtime admission identities, builder trust-generation provenance, raw response digest, verified reference, provider proof, state and observation epoch.

All provider responses, verifier receipts, verdicts, attestations and proof envelopes remain `authority=false`. External truth never becomes ambient Koschei authority.

## PROTECTS AGAINST

- treating local callback completion as provider finality,
- caller-selected provider state/reference/proof after native verification,
- raw response/reference rebinding,
- cross-verifier receipt relabeling,
- using a stale builder trust generation for new provider-native verification,
- dropping trust-generation identity from provider-native provenance,
- conflating historical authenticity with current operational trust status.

## DOES NOT PROTECT AGAINST

- a trusted but buggy/malicious verifier,
- compromised root/reproducibility/provider trust-role keys,
- full rollback of the authoritative generation state/store,
- provider reorg/reversal,
- host/runtime compromise or measure-A/execute-B TOCTOU,
- Pi/provider network correctness outside the verifier boundary.

## ASSUMPTIONS

- adapter/verifier build admission is fail-closed,
- supplied generation state/store is authoritative for current operational validation,
- verifier artifact measurement corresponds to executed code,
- provider-native transport/proof verification is correct,
- historical integrity is never treated as a capability or fresh permission.

## FAILURE MODE

If the authoritative generation store is rolled back, stale trust generations may again appear current. The restart-durable SQLite store narrows normal restart loss but cannot detect restoration of a complete older valid database snapshot without an external/hardware monotonic witness.

Historical integrity proves the recorded chain is internally authentic; it cannot prove the original trusted verifier/root was honest.

## NEXT

1. Add a hardware/external monotonic witness for rollback-resistant current-generation validation.
2. Define archival key/manifests retention policy for historical verification.
3. Close measure-A/execute-B with immutable runtime load handles.
4. Implement one real provider-specific attestation adapter outside Lang core.
5. Produce canonical `ks-local-validate --profile full` evidence before merge.
