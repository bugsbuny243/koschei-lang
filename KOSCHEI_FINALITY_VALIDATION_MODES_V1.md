# KOSCHEI FINALITY VALIDATION MODES V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / HISTORICAL INTEGRITY SEPARATED FROM CURRENT OPERATIONAL VALIDITY

## PURPOSE

A proof can be authentic as issued while no longer satisfying today's trust policy. Koschei V1 now separates those questions explicitly.

### Historical integrity

`assert_external_finality_historical_integrity_v1(...)`

asks:

> Was this exact finality proof chain internally authentic and cryptographically/provenance-bound as issued?

It validates:

- native effect/execution proof lineage,
- exact verifier artifact/build/runtime admission,
- authenticated reproducibility receipt integrity,
- provider-native receipt HMAC and exact raw response/reference binding,
- provider verdict,
- finality attestation,
- external finality envelope field bindings and aggregate digest.

Historical integrity deliberately does **not** require builder trust-anchor generations to still be current today.

### Current operational validity

`ExternalFinalityProofEnvelopeV1.assert_valid(...)`

asks:

> Is the proof authentic **and** are its builder trust-anchor generations still current under the supplied operational trust state/store?

It performs the sealed lineage checks and additionally requires builder A/B current-generation bindings through the provider-native generation guard.

## EXAMPLE

1. A provider-finalized proof is issued under trust generation 41.
2. The proof remains historically authentic.
3. Operations advance the relevant trust anchor to generation 42 because generation 41 is revoked or superseded.
4. Current operational validation of the old generation-41 proof fails.
5. Historical integrity validation may still succeed if the original proof has not been altered.

This distinction avoids two incorrect claims:

- "old proof fails current policy, therefore it was forged",
- "old proof is historically authentic, therefore it may authorize a new action today".

Neither is valid.

## PROTECTS AGAINST

- conflating historical authenticity with current authorization/trust status,
- rewriting history merely because a verifier/root generation is superseded,
- accepting historical proof integrity as permission for a new privileged effect,
- proof tampering hidden behind an archival-validation mode.

## DOES NOT PROTECT AGAINST

- a malicious verifier/root that was trusted when the historical proof was issued,
- compromised signing/HMAC keys,
- a false historical timeline if trusted issuance components lied at issuance,
- local monotonic-store snapshot rollback for current validation,
- provider reorg/reversal after an originally valid finalized observation.

## ASSUMPTIONS

- historical verification keys/provenance required by V1 remain available and authentic,
- the caller intentionally chooses historical vs current operational semantics,
- current operational consumers provide the authoritative generation state/store,
- historical integrity is never treated as a fresh capability or execution permit.

## FAILURE MODE

Historical integrity proves internal consistency and authentication of the recorded chain, not that the policy which admitted the original verifier remains acceptable today.

Current operational validation proves current-policy compatibility only relative to the supplied generation state/store. If that state/store is rolled back, current validity can also be misrepresented until a hardware/external monotonic witness is added.

## NEXT

1. Add hardware/external monotonic witness evidence for current operational validation.
2. Define archival key-retention and verifier-manifest retention policy.
3. Add a machine-readable validation-mode result receipt rather than relying only on exceptions.
4. Add root-key rotation and multi-root authorization semantics.
5. Produce canonical `ks-local-validate --profile full` evidence before merge.
