# KOSCHEI MONOTONIC WITNESS V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / PROVIDER-NEUTRAL ABI + RUNTIME-OWNED CHALLENGE + RECEIPT + GENERATION GUARD WIRED / REAL WITNESS PROVIDER EXTERNAL

## PURPOSE

`SqliteTrustAnchorGenerationStoreV1` survives ordinary process restart and authenticates its append history, but a complete older VM/disk/database snapshot can restore an older internally valid HMAC chain.

A local store cannot prove that a newer state existed if every local record of that newer state was rolled back with the snapshot.

V1 therefore adds an independent witness boundary:

`local trust-anchor generation state`
`+ RuntimeMonotonicWitnessChallengeV1`
`+ raw external witness response`
`+ admitted witness-verifier artifact`
`-> MonotonicWitnessReceiptV1`
`-> WitnessConfirmedGenerationStateV1`
`-> reproducibility current-generation guard`
`-> provider-native verification`

The provider-native receipt seals the exact builder-A and builder-B witness receipt digests when both builder generation states are witness-confirmed.

## ABI

`MonotonicWitnessAbiV1` binds:

- witness provider id,
- witness protocol/profile id,
- schema version,
- exact witness-verifier implementation digest,
- `authority=false`.

The generic Lang core does not parse TPM, cloud control-plane, transparency-log or consensus-specific response formats.

## RUNTIME-OWNED CHALLENGE

Production witness freshness must not depend on application-selected nonce bytes.

`issue_runtime_monotonic_witness_challenge_v1(...)`:

- generates 32 random bytes with Python `secrets.token_bytes`,
- binds one anchor id,
- binds issuance and expiry epochs,
- authenticates the challenge receipt with a dedicated runtime witness-challenge key,
- carries `authority=false`.

The sanctioned production bridge is:

`RuntimeMonotonicWitnessChallengeV1`
`-> verify_monotonic_witness_with_runtime_challenge_v1(...)`
`-> provider-specific witness verifier callback`
`-> MonotonicWitnessReceiptV1`

The lower `verify_monotonic_witness_response_v1(...)` raw-challenge function remains a bootstrap implementation primitive. Production APIs must not expose it as a way for untrusted application code to choose challenge bytes when snapshot-rollback resistance is required.

An expired, forged or wrong-anchor runtime challenge is rejected before the provider-specific witness callback executes.

## VERIFIER RESULT

A trusted provider-specific verifier derives:

- anchor id,
- generation,
- manifest digest,
- provider witness counter/checkpoint sequence,
- observed epoch,
- expiry epoch,
- the exact runtime challenge,
- provider proof bytes.

The caller does not separately choose the witnessed generation or manifest in the sanctioned verification path.

## FRESHNESS

The provider-specific verifier receives both:

- exact raw witness response bytes,
- exact runtime-owned expected challenge bytes.

The returned result must bind the exact expected challenge. The authenticated `MonotonicWitnessReceiptV1` commits:

- ABI identity,
- verifier implementation measurement,
- raw-response digest,
- challenge digest,
- anchor/generation/manifest,
- witness counter,
- observation/expiry epochs,
- provider-proof digest.

Generic core can verify equality and provenance. It cannot determine whether a provider-specific verifier correctly validated a remote signature/challenge unless that verifier actually implements the provider protocol correctly.

## EXACT LOCAL/WITNESS AGREEMENT

`WitnessConfirmedGenerationStateV1.assert_current_binding(...)` first verifies the local state, then verifies the external witness receipt and requires exact equality of:

- anchor id,
- generation,
- manifest digest.

V1 is intentionally fail-closed. A local generation ahead of the witness is not silently accepted, and a witness generation ahead of the local store is treated as rollback/divergence.

Example:

`local restored snapshot = generation 39`
`external witness = generation 42`
`=> reject`

`confirm_generation_state_with_runtime_witness_v1(...)` additionally requires the runtime challenge receipt itself to remain authenticated, live and anchor-scoped before constructing the witnessed state.

## PROVIDER-NATIVE PROVENANCE

If both builder generation states are `WitnessConfirmedGenerationStateV1`, `ProviderNativeVerificationReceiptV1` additionally seals:

- builder-A monotonic witness receipt digest,
- builder-B monotonic witness receipt digest.

Using a witness-backed state for only one builder and a local-only state for the other is rejected before the provider callback.

The existing local-only bootstrap path remains available and records empty witness digests. It must not be described as snapshot-rollback resistant.

## HISTORICAL INTEGRITY

Witness liveness and historical integrity are different questions.

For witnessed provider-native receipts, historical validation requires archived `MonotonicWitnessEvidenceBundleV1` inputs containing:

- witness receipt,
- witness ABI,
- verifier artifact bytes,
- raw response bytes,
- challenge bytes.

The verifier HMAC key remains separate from the archive bundle.

Historical validation rechecks receipt integrity but does not require the old witness receipt to still be live today.

## PROTECTS AGAINST

- complete local generation-store rollback being accepted when an independent fresh witness remembers a newer generation,
- application-selected stale challenge bytes on the sanctioned runtime-owned challenge path,
- replay of a stale witness response when the provider-specific verifier correctly binds the fresh runtime challenge,
- witness verifier artifact relabeling,
- raw witness-response rebinding,
- challenge rebinding,
- wrong-anchor challenge reuse,
- generation/manifest relabeling after receipt issuance,
- dropping witness identity from witnessed provider-native provenance,
- asymmetric one-builder-only witness hardening on the provider-native sanctioned path.

## DOES NOT PROTECT AGAINST

- a witness provider rolled back or compromised together with the local host,
- malicious/buggy provider-specific witness verifier code that is nevertheless admitted,
- compromised witness-verifier or runtime challenge key,
- failure of the OS/runtime CSPRNG used by `secrets.token_bytes`,
- stolen live runtime challenge before provider verification when the provider protocol itself is weak,
- witness service equivocation unless the provider/protocol exposes a mechanism that detects it,
- network partition or witness unavailability,
- local host/runtime compromise after all checks,
- measure-A/execute-B TOCTOU,
- durable execution-permit replay ledger rollback,
- hardware monotonicity by itself.

## ASSUMPTIONS

- the witness authority has failure/rollback independence from the local generation store,
- the provider-specific verifier authenticates the real provider response and verifies challenge binding,
- verifier artifact bytes measured are the bytes executed,
- runtime challenge key and RNG are protected by the runtime trust boundary,
- witness-verifier, challenge and provider-native trust keys are protected and role-separated,
- current operational consumers use witness-confirmed generation states when making snapshot-rollback-resistance claims.

## FAILURE MODE

If an attacker can restore both the local state and the external witness to the same old checkpoint, Koschei sees two matching old states and cannot infer that a newer state ever existed.

If the witness verifier lies, Koschei can prove which verifier identity, raw response, challenge and result were used; it cannot turn a false witness statement into truth.

If the witness is unavailable, exact fail-closed policy denies current witnessed operation. Availability policy must not silently downgrade to local-only validation if the operation requires snapshot-rollback detection.

## NEXT

1. Define witness-provider admission/revocation policy and explicit key-role equality rejection.
2. Add one real external witness adapter outside Lang core, such as a transparency/checkpoint service or hardware/cloud-backed monotonic primitive.
3. Bind witness-verifier build provenance through the same Verified-IR/reproducible-build chain without recursive trust collapse.
4. Add immutable runtime load handles to reduce measure-A/execute-B TOCTOU.
5. Move durable execution-permit replay state to a similarly externally witnessed/monotonic boundary where required.
6. Produce canonical `ks-local-validate --profile full` evidence before merge.
