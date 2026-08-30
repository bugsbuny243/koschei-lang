# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / CURRENT-GENERATION + OPTIONAL EXTERNAL-WITNESS GUARD WIRED / PROVIDER NETWORK ADAPTER EXTERNAL

## PURPOSE

`effect-completed` is local. Provider finality must be derived from exact raw provider bytes through a known verifier contract, not caller-selected state/reference/proof.

Sanctioned verifier chain:

`VerifiedIrBuildInputV1`
`-> signed ToolchainProvenanceV1`
`-> root-admitted remote-attested builder A`
`-> root-admitted remote-attested builder B`
`-> VerifierReproducibleBuildReceiptV1`
`-> exact artifact build provenance`
`-> ProviderAdapterAbiV1`
`-> VerifierReproducibleRuntimeAdmissionV1`
`-> current generation guard`
`-> optional external monotonic-witness confirmation for both builders`
`-> raw provider response verification`
`-> ProviderNativeVerificationReceiptV1`

Base runtime admission or a previously minted reproducible gate is not enough. Before the provider verifier callback executes, the authenticated reproducibility receipt is checked against builder A/B current trust-anchor generation state.

## CURRENT-GENERATION GUARD

`verifier_generation_guard_v1` authenticates the reproducibility receipt HMAC using the reproducibility key and checks:

- builder A anchor id + generation + manifest digest is current,
- builder B anchor id + generation + manifest digest is current.

If either anchor advances to generation N+1, a receipt/gate bound to generation N cannot be used for new provider-native verification through that state/store.

`ProviderNativeVerificationReceiptV1` binds both builder anchor/generation/manifest identities so provider verification provenance does not discard the trust-generation state under which it executed.

## EXTERNAL MONOTONIC WITNESS MODE

A complete old local-database or VM snapshot can restore an old but internally valid local generation chain. `MonotonicWitnessV1` addresses this only when an independent external witness remembers a newer state.

For a witnessed provider-native execution, both builder generation-state inputs must be `WitnessConfirmedGenerationStateV1` instances. Each confirms exact equality among:

- local current anchor/generation/manifest,
- reproducibility receipt anchor/generation/manifest,
- fresh external witness anchor/generation/manifest.

Using one witnessed builder and one local-only builder is rejected before callback execution.

When both are witnessed, `ProviderNativeVerificationReceiptV1` additionally HMAC-seals:

- builder-A monotonic witness receipt digest,
- builder-B monotonic witness receipt digest.

The full external-finality envelope already commits the provider-native receipt digest, so witness provenance is transitively committed by finality proofs without duplicating those fields at every layer.

Local-only bootstrap verification remains supported and records empty witness digests. It must not be described as snapshot-rollback resistant.

## HISTORICAL VALIDATION

Historical provider-native validation does not require an old witness receipt to remain live today.

If the provider-native receipt contains witness digests, historical validation requires archived `MonotonicWitnessEvidenceBundleV1` evidence for both builders and rechecks each witness receipt's:

- ABI/artifact identity,
- raw response digest,
- challenge digest,
- canonical anchor/generation/manifest result,
- provider-proof digest,
- receipt authentication.

This preserves audit integrity without turning old witness freshness into current authority.

## V1 REFERENCE CONTRACT

Successful effect callback bytes are the canonical expected external reference. For Pi payment V1 these bytes are canonical txid bytes. Provider-native verification must return the same reference or fail before verdict issuance.

No unverified Pi response schema is hard-coded in Lang core.

## PROTECTS AGAINST

- caller-selected provider finality state/reference/proof,
- raw provider response rebinding,
- verifier artifact substitution,
- caller-selected build-input/toolchain digests,
- one builder alone claiming reproducibility,
- one measured builder environment being counted twice,
- using an old builder trust generation for new provider verification after a newer generation is known,
- forged compact generation fields without the reproducibility receipt key,
- dropping builder trust-generation identity from provider-native receipt provenance,
- accepting a restored older local generation snapshot when both required independent external witnesses report newer bindings,
- dropping witnessed-generation provenance after callback execution.

## DOES NOT PROTECT AGAINST

- malicious/buggy provider verifier semantics accepted by policy,
- compromised root/toolchain/environment attestation authorities,
- two attacker-controlled but distinct attested environments,
- rollback/compromise of both local state and its supposedly independent witness,
- witness service equivocation unless the selected provider protocol detects it,
- shared hypervisor/host compromise,
- false provider/network data accepted by the verifier,
- measure-A/execute-B runtime TOCTOU,
- protected-key or host/runtime compromise.

## ASSUMPTIONS

- current generation states/stores are authoritative for the relevant anchors,
- witnessed mode uses external witnesses with failure/rollback independence from local state,
- witness verifier correctly authenticates provider response and challenge binding,
- reproducibility, generation-store, witness-verifier and provider-native keys are protected and role-separated,
- provider schema/version identity is pinned and reviewed,
- provider-native verifier performs real authenticated provider verification,
- final consumers use current operational validation when current trust policy matters.

## FAILURE MODE

A stale generation is detectable only relative to trusted state that did not roll back with it. If an attacker can restore the local store and the external witness to the same old valid state, Koschei cannot infer that a newer state existed.

A malicious admitted witness verifier can also lie consistently. Koschei can bind the exact verifier identity, challenge and raw response used; it cannot manufacture the truth of an external statement.

## NEXT

1. Add witness-provider admission/revocation and explicit trust-key-role separation.
2. Move fresh witness challenge generation into runtime custody.
3. Close runtime load-handle TOCTOU.
4. Pin one real provider-specific witness/attestation adapter outside Lang core.
5. Move durable permit replay/audit state into a similarly monotonic boundary where required.
6. Produce canonical `ks-local-validate --profile full` evidence before merge.
