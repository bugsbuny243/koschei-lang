# KOSCHEI TRUST ANCHOR GENERATION STORE V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / RESTART-DURABLE LOCAL STATE / NOT HARDWARE ROLLBACK-RESISTANT

## PURPOSE

`TrustAnchorGenerationStateV1` prevents rollback only while one process-local state object survives. `SqliteTrustAnchorGenerationStoreV1` provides the same `observe`, `assert_current_binding`, `assert_current` and `highest_generation` surface with transactional persistence across normal process restart.

## MODEL

Per anchor, the store maintains an append-only logical history:

`revision -> generation -> manifest_digest -> previous_record_mac -> record_mac`

Each row is HMAC-authenticated under a dedicated generation-store key. SQLite is configured with WAL journaling and `synchronous=FULL` and updates execute under `BEGIN IMMEDIATE` transactions.

## RULES

- lower generation than current -> rollback reject,
- same generation + different manifest digest -> equivocation reject,
- same generation + same manifest -> idempotent,
- higher authenticated generation -> append a new authenticated history row,
- broken history link or invalid row HMAC -> fail closed,
- reopening the database preserves the highest observed generation.

The store is duck-compatible with the existing trust-anchor runtime-admission API; no second authority system is introduced.

## DOWNSTREAM CURRENT-GENERATION ENFORCEMENT

Current-generation checks now continue past remote-attestation issuance:

`RemoteAttestationEvidenceV1`
`-> BuilderEnvironmentAttestationV1`
`-> VerifierBuilderObservationV1`
`-> VerifierReproducibleBuildReceiptV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> ProviderNativeVerificationReceiptV1`
`-> current operational ExternalFinalityProofEnvelopeV1 validation`

The provider-native callback is rejected before execution if either builder's authenticated reproducibility receipt points at a trust-anchor generation that is no longer current.

## PROTECTS AGAINST

- losing monotonic generation solely because the process restarts normally,
- lower-generation manifest reuse after a newer generation is persisted,
- same-generation manifest equivocation,
- ordinary SQLite row tampering when the generation-store key remains protected,
- using stale generation builder/reproducibility evidence for new provider-native verification,
- current operational finality validation under stale builder trust generations.

## DOES NOT PROTECT AGAINST

- VM/filesystem/disk snapshot rollback that restores the whole valid database to an earlier state,
- deletion of the database followed by re-bootstrap from an old manifest,
- forked replicas with no external monotonic coordination,
- compromised generation-store key,
- compromised offline root-signing key,
- malicious manifests intentionally signed by the root authority,
- historical-proof semantics; V1 current validation intentionally follows current trust policy and a separate archival validation mode is not yet defined.

## ASSUMPTIONS

- filesystem and SQLite durability semantics are functioning as configured,
- the generation-store key is protected independently of the database file,
- callers use one authoritative store or a higher-level coordinated monotonic witness,
- trust-anchor manifests are authenticated before insertion.

## FAILURE MODE

The local authenticated history proves internal continuity of the database that is presented to the runtime. It cannot prove that the presented database is the newest database that ever existed. An attacker capable of restoring a complete older database snapshot can also restore a previously valid HMAC chain.

Therefore `SqliteTrustAnchorGenerationStoreV1` is durable local monotonic state, not hardware/external rollback-resistant state.

## NEXT

1. Add a hardware or external monotonic witness interface whose state cannot be rolled back with the local database.
2. Bind witness sequence/freshness into trust-anchor runtime admission.
3. Define historical/audit proof validation separately from current operational trust validation.
4. Add root-key rotation and threshold authorization.
5. Close measure-A/execute-B with immutable runtime load handles.
6. Produce canonical `ks-local-validate --profile full` evidence before merge.
