# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / CURRENT-GENERATION REPRODUCIBILITY GUARD WIRED / PROVIDER NETWORK ADAPTER EXTERNAL

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
`-> verifier_generation_guard_v1`
`-> raw provider response verification`
`-> ProviderNativeVerificationReceiptV1`

Base runtime admission or a previously minted reproducible gate is not enough. Before the provider verifier callback executes, the authenticated reproducibility receipt is checked against builder A/B current trust-anchor generation state.

## CURRENT-GENERATION GUARD

`verifier_generation_guard_v1` authenticates the reproducibility receipt HMAC using the reproducibility key and checks:

- builder A anchor id + generation + manifest digest is current,
- builder B anchor id + generation + manifest digest is current.

If either anchor advances to generation N+1, a receipt/gate bound to generation N cannot be used for new provider-native verification through that state/store.

`ProviderNativeVerificationReceiptV1` binds both builder anchor/generation/manifest identities so provider verification provenance does not discard the trust-generation state under which it executed.

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
- dropping builder trust-generation identity from provider-native receipt provenance.

## DOES NOT PROTECT AGAINST

- malicious/buggy provider verifier semantics accepted by policy,
- compromised root/toolchain/environment attestation authorities,
- two attacker-controlled but distinct attested environments,
- full rollback of the authoritative monotonic state/store,
- shared hypervisor/host compromise,
- false provider/network data accepted by the verifier,
- measure-A/execute-B runtime TOCTOU,
- protected-key or host/runtime compromise.

## ASSUMPTIONS

- current generation states/stores are authoritative for the relevant anchors,
- reproducibility key and generation-store keys are protected,
- provider schema/version identity is pinned and reviewed,
- provider-native verifier performs real authenticated provider verification,
- final consumers use current operational validation when current trust policy matters.

## FAILURE MODE

A stale generation is only detectable relative to the supplied authoritative generation state/store. If that state itself is rolled back to an older valid snapshot, the provider-native generation guard can also be fooled. SQLite local durability therefore narrows restart rollback but does not replace hardware/external monotonic evidence.

## NEXT

1. Add hardware/external monotonic witness evidence for rollback-resistant generation state.
2. Separate historical/audit validation from current operational validation.
3. Close runtime load-handle TOCTOU.
4. Pin one real provider-specific attestation adapter outside Lang core.
5. Move durable replay/audit state into runtime custody.
6. Produce canonical `ks-local-validate --profile full` evidence before merge.
