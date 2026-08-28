# KOSCHEI TRUST ANCHOR / ROOT ADMISSION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NON-RECURSIVE ROOT OF TRUST / PROCESS-LOCAL GENERATION ANTI-ROLLBACK

## PURPOSE

Remote-attestation verifier trust cannot recursively depend on the same remote-attestation
pipeline that it is responsible for establishing. V1 introduces an explicit bootstrap
trust anchor for attestation-verifier artifacts and attestation trust roots, plus a
monotonic manifest-generation state that rejects rollback inside one live state instance.

Sanctioned bootstrap chain:

`offline/root signing authority`
`-> TrustAnchorManifestV1(generation)`
`-> TrustAnchorGenerationStateV1.observe(...)`
`-> exact AttestationVerifierAbiV1`
`-> exact attestation-verifier artifact bytes`
`-> TrustAnchorRuntimeAdmissionV1(generation)`
`-> provider-specific attestation verifier callback`
`-> allowed trust-root check`
`-> RemoteAttestationEvidenceV1(anchor + generation)`

The root layer is intentionally non-recursive. It does not require builder remote
attestation in order to admit the attestation verifier that validates builder evidence.

## TRUST ANCHOR MANIFEST

`TrustAnchorManifestV1` binds:

- anchor identity,
- monotonic generation,
- exact attestation-verifier ABI digest,
- exact verifier implementation digest,
- allowed trust-root ids,
- revoked trust-root ids,
- valid-from epoch,
- expires-before epoch,
- verifier revocation flag,
- authority=false.

The manifest is authenticated under a dedicated root-signing key. Generation is part of
the authenticated payload and cannot be relabeled without invalidating the manifest.

## GENERATION STATE

`TrustAnchorGenerationStateV1` keeps the highest observed `(generation, manifest_digest)`
for each anchor id.

Rules:

- lower generation than the highest observed generation -> reject as rollback,
- same generation with a different manifest digest -> reject as equivocation,
- same generation with the same digest -> idempotent,
- higher authenticated generation -> advance current state.

`TrustAnchorRuntimeAdmissionV1` can validate only against the current observed manifest.
After generation N+1 has been observed, generation N can no longer be used to admit the
attestation verifier or mint new remote-attestation evidence through the same state.

V1 state is process-local memory. It is NOT durable, fork-safe, crash-safe or hardware
monotonic storage.

## RUNTIME ADMISSION

`TrustAnchorRuntimeAdmissionV1` binds:

- exact root manifest digest,
- exact manifest generation,
- exact attestation-verifier ABI,
- exact measured verifier artifact,
- admission epoch,
- admitted=true,
- authority=false.

A verifier callback is not executed by the sanctioned remote-attestation path unless the
root manifest, generation state and runtime admission all validate at the current epoch.

## TRUST ROOT POLICY

After the provider-specific verifier returns a canonical result, its `trust_root_id` must
be present in the manifest allowlist and absent from the revocation set before
`RemoteAttestationEvidenceV1` can be sealed.

The resulting remote evidence binds:

- trust-anchor id,
- trust-anchor generation,
- trust-anchor manifest digest,
- trust-anchor runtime-admission digest,
- attestation-verifier ABI and implementation identities.

## PROTECTS AGAINST

- recursive self-justification of the attestation verifier,
- verifier artifact substitution before attestation parsing,
- using an ABI/verifier artifact not approved by the root manifest,
- expired root manifests,
- explicitly revoked verifier manifests,
- unapproved or revoked attestation trust roots,
- generation relabeling,
- rollback to an older manifest after a newer generation has been observed in the same state,
- same-generation manifest equivocation,
- dropping root generation/manifest/runtime-admission identity from newly sealed remote evidence.

## DOES NOT PROTECT AGAINST

- compromised offline/root signing key,
- malicious verifier artifact intentionally approved by the root authority,
- malicious or mistaken trust roots intentionally allowlisted,
- provider-specific verifier implementation bugs,
- process restart or storage rollback that loses `TrustAnchorGenerationStateV1`,
- forked processes holding divergent generation states,
- replay of already-issued still-live remote evidence unless downstream consumers also consult monotonic state,
- host/runtime compromise after artifact measurement,
- measure-A/execute-B TOCTOU.

## ASSUMPTIONS

- the root-signing key is protected independently from online runtime keys,
- production replaces or persists generation state in rollback-resistant storage,
- verifier artifact measurement is canonical,
- the runtime executes the exact artifact admitted,
- root/trust policy updates and revocations are delivered before affected evidence is trusted.

## FAILURE MODE

The bootstrap trust anchor is an explicit trusted computing base. Koschei proves which
root policy, generation and verifier artifact were admitted; it does not prove that the
offline root authority itself was honest or uncompromised.

The current anti-rollback state protects one live state instance only. If an attacker can
restore an older process snapshot, fork the state, or erase the state and restart from an
older still-live manifest, V1 cannot detect that rollback. Already-issued remote evidence
also remains valid until its own expiry unless later consumers are bound to the monotonic
state.

## NEXT

1. Back generation state with durable rollback-resistant monotonic storage.
2. Require downstream builder/reproducibility consumers to compare remote-evidence generation against current trust-anchor state.
3. Bind revocation state to trusted epoch/monotonic storage.
4. Add root-key rotation and threshold/multi-root authorization.
5. Bind runtime execution to immutable load handles to close measure-A/execute-B TOCTOU.
6. Implement one real provider-specific attestation adapter outside Lang core.
7. Produce canonical `ks-local-validate --profile full` evidence before merge.
