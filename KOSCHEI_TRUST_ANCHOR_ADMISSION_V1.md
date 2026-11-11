# KOSCHEI TRUST ANCHOR / ROOT ADMISSION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NON-RECURSIVE ROOT OF TRUST / GENERATION-LOCKED DOWNSTREAM VALIDATION

## PURPOSE

Remote-attestation verifier trust cannot recursively depend on the same remote-attestation pipeline that it establishes. V1 introduces an explicit bootstrap trust anchor, monotonic manifest generations, and downstream current-generation enforcement.

Sanctioned chain:

`offline/root signing authority`
`-> TrustAnchorManifestV1(generation)`
`-> generation state/store.observe(...)`
`-> exact AttestationVerifierAbiV1`
`-> exact attestation-verifier artifact`
`-> TrustAnchorRuntimeAdmissionV1(generation)`
`-> raw remote evidence verification`
`-> RemoteAttestationEvidenceV1(anchor + generation)`
`-> BuilderEnvironmentAttestationV1(anchor + generation)`
`-> VerifierBuilderObservationV1(anchor + generation)`
`-> VerifierReproducibleBuildReceiptV1(A/B anchor + generation)`
`-> current-generation guard`
`-> provider-native verification`
`-> current operational finality validation`

The root layer is intentionally non-recursive.

## TRUST ANCHOR MANIFEST

`TrustAnchorManifestV1` binds anchor identity, monotonic generation, exact attestation-verifier ABI and implementation digests, allowed/revoked trust roots, validity epochs, verifier revocation state, and `authority=false` under a dedicated root-signing key.

Generation is inside the authenticated payload and cannot be relabeled without invalidating the manifest.

## GENERATION STATE

`TrustAnchorGenerationStateV1` tracks the highest observed `(generation, manifest_digest)` per anchor in process memory.

Rules:

- lower generation -> rollback reject,
- same generation with different digest -> equivocation reject,
- same generation with same digest -> idempotent,
- higher authenticated generation -> advance current state.

`assert_current_binding(anchor_id, generation, manifest_digest)` is the compact downstream check used by remote evidence and reproducibility validation.

## RESTART-DURABLE LOCAL STORE

`SqliteTrustAnchorGenerationStoreV1` implements the same state surface using SQLite transactional persistence and HMAC-chained per-anchor history. It survives normal process restart and detects ordinary row/history tampering when its store key remains protected.

It is NOT hardware rollback-resistant. Restoring a complete older database snapshot can restore an older previously valid HMAC chain. See `KOSCHEI_TRUST_ANCHOR_GENERATION_STORE_V1.md`.

## DOWNSTREAM GENERATION ENFORCEMENT

Remote evidence now exposes `assert_current_generation(...)`.

`BuilderEnvironmentAttestationV1` binds and re-validates:

- trust-anchor id,
- trust-anchor generation,
- trust-anchor manifest digest,
- exact remote-attestation evidence digest.

`VerifierBuilderObservationV1` and `VerifierReproducibleBuildReceiptV1` carry the same generation identities forward. A compact `verifier_generation_guard_v1` authenticates the reproducibility receipt HMAC and checks builder A/B against current generation states before provider-native verification.

After generation N+1 is observed, generation N evidence cannot be used to mint/validate a current builder observation, reproducibility admission, provider-native verification receipt, or current operational finality proof through the same authoritative state/store.

## RUNTIME ADMISSION

`TrustAnchorRuntimeAdmissionV1` binds exact manifest digest, exact generation, exact ABI, exact measured verifier artifact, admission epoch, `admitted=true`, and `authority=false`.

The attestation verifier callback is not executed unless the manifest, current generation state/store, runtime admission and exact artifact all validate first.

## PROTECTS AGAINST

- recursive self-justification of the attestation verifier,
- verifier artifact substitution before parsing,
- expired/revoked verifier manifests,
- unapproved/revoked trust roots,
- manifest generation relabeling,
- lower-generation rollback after a newer generation is observed,
- same-generation equivocation,
- stale generation builder/reproducibility evidence being reused for new provider-native verification,
- stale generation use during current operational finality validation,
- ordinary local generation-history tampering when the local store key is protected.

## DOES NOT PROTECT AGAINST

- compromised offline/root signing key,
- intentionally approved malicious verifier/root policy,
- provider-specific verifier bugs,
- full VM/disk/database snapshot rollback,
- deletion/re-bootstrap of local durable state from an older manifest,
- forked replicas with divergent stores and no external monotonic witness,
- compromised generation-store key,
- measure-A/execute-B runtime TOCTOU,
- host/runtime compromise.

## ASSUMPTIONS

- root-signing and local generation-store keys are protected independently,
- production uses one authoritative monotonic state or a stronger coordinated witness,
- verifier artifact measurement is canonical,
- the runtime executes the exact artifact admitted,
- revocation/generation updates are delivered before affected evidence is trusted.

## FAILURE MODE

Koschei can prove which root policy, generation and verifier artifact were presented and whether that generation is current in the supplied authoritative state/store. It cannot prove that a locally presented database is globally the newest state ever created without hardware-backed or external monotonic evidence.

Current operational validation follows current trust policy. Historical/audit proof validation semantics are not yet separated; an old proof may fail current validation after a generation advance even though it was valid when issued.

## NEXT

1. Add hardware/external monotonic witness evidence so database snapshot rollback is detectable.
2. Define separate historical/audit validation semantics.
3. Add root-key rotation and threshold/multi-root authorization.
4. Bind builder keys to attested workload identity.
5. Bind runtime execution to immutable load handles to close measure-A/execute-B TOCTOU.
6. Implement one real provider-specific attestation adapter outside Lang core.
7. Produce canonical `ks-local-validate --profile full` evidence before merge.
