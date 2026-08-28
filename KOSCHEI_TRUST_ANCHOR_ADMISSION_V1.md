# KOSCHEI TRUST ANCHOR / ROOT ADMISSION V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / NON-RECURSIVE ROOT OF TRUST

## PURPOSE

Remote-attestation verifier trust cannot recursively depend on the same remote-attestation
pipeline that it is responsible for establishing. V1 introduces an explicit bootstrap
trust anchor for attestation-verifier artifacts and attestation trust roots.

Sanctioned bootstrap chain:

`offline/root signing authority`
`-> TrustAnchorManifestV1`
`-> exact AttestationVerifierAbiV1`
`-> exact attestation-verifier artifact bytes`
`-> TrustAnchorRuntimeAdmissionV1`
`-> provider-specific attestation verifier callback`
`-> allowed trust-root check`
`-> RemoteAttestationEvidenceV1`

The root layer is intentionally non-recursive. It does not require builder remote
attestation in order to admit the attestation verifier that validates builder evidence.

## TRUST ANCHOR MANIFEST

`TrustAnchorManifestV1` binds:

- anchor identity,
- exact attestation-verifier ABI digest,
- exact verifier implementation digest,
- allowed trust-root ids,
- revoked trust-root ids,
- valid-from epoch,
- expires-before epoch,
- verifier revocation flag,
- authority=false.

The manifest is authenticated under a dedicated root-signing key.

## RUNTIME ADMISSION

`TrustAnchorRuntimeAdmissionV1` binds:

- exact root manifest digest,
- exact attestation-verifier ABI,
- exact measured verifier artifact,
- admission epoch,
- admitted=true,
- authority=false.

A verifier callback is not executed by the sanctioned remote-attestation path unless the
root manifest and runtime admission both validate at the current epoch.

## TRUST ROOT POLICY

After the provider-specific verifier returns a canonical result, its `trust_root_id` must
be present in the manifest allowlist and absent from the revocation set before
`RemoteAttestationEvidenceV1` can be sealed.

The resulting remote evidence binds both the trust-anchor manifest digest and the runtime
admission digest so the bootstrap provenance is not dropped after verification.

## PROTECTS AGAINST

- recursive self-justification of the attestation verifier,
- verifier artifact substitution before attestation parsing,
- using an ABI/verifier artifact not approved by the root manifest,
- expired root manifests,
- explicitly revoked verifier manifests,
- unapproved or revoked attestation trust roots,
- dropping root-manifest/runtime-admission identity from remote evidence.

## DOES NOT PROTECT AGAINST

- compromised offline/root signing key,
- malicious verifier artifact intentionally approved by the root authority,
- malicious or mistaken trust roots intentionally allowlisted,
- provider-specific verifier implementation bugs,
- rollback to an older still-valid manifest without durable monotonic policy,
- host/runtime compromise after artifact measurement,
- measure-A/execute-B TOCTOU.

## ASSUMPTIONS

- the root-signing key is protected independently from online runtime keys,
- manifest distribution is authenticated and production stores enforce monotonic policy,
- verifier artifact measurement is canonical,
- the runtime executes the exact artifact admitted,
- root/trust policy updates and revocations are delivered before affected evidence is trusted.

## FAILURE MODE

The bootstrap trust anchor is an explicit trusted computing base. Koschei proves which
root policy and verifier artifact were admitted; it does not prove that the offline root
authority itself was honest or uncompromised.

Current revocation is manifest-scoped, not backed by a durable monotonic generation or
anti-rollback store. An attacker able to roll runtime state back to an older still-live
manifest may bypass a newer revocation decision.

## NEXT

1. Add manifest generation/sequence numbers and durable anti-rollback enforcement.
2. Bind revocation state to trusted epoch/monotonic storage.
3. Add root-key rotation and threshold/multi-root authorization.
4. Bind runtime execution to immutable load handles to close measure-A/execute-B TOCTOU.
5. Implement one real provider-specific attestation adapter outside Lang core.
6. Produce canonical `ks-local-validate --profile full` evidence before merge.
