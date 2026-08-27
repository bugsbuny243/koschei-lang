# KOSCHEI PROVIDER NATIVE VERIFIER V1

Status: IMPLEMENTED BOOTSTRAP PROTOTYPE / VERIFIED-IR + SIGNED-TOOLCHAIN + DISTINCT-ENVIRONMENT REPRODUCIBILITY GATE WIRED / PROVIDER NETWORK ADAPTER REMAINS EXTERNAL

## PURPOSE

`effect-completed` is local. Provider finality must be derived from raw provider bytes
through a known verifier contract, not caller-selected state/reference/proof.

Before provider-native verification, the verifier artifact must pass:

`VerifiedIrBuildInputV1`
`-> signed ToolchainProvenanceV1`
`-> builder A + BuilderEnvironmentAttestationV1`
`-> builder B + BuilderEnvironmentAttestationV1`
`-> VerifierReproducibleBuildReceiptV1`
`-> exact artifact build provenance`
`-> ProviderAdapterAbiV1`
`-> reproducibility-gated runtime admission`
`-> raw provider response verification`

The two builders must have distinct logical identities and distinct measured environment
identities. Base runtime admission alone is insufficient.

## V1 REFERENCE CONTRACT

The successful effect callback bytes are the canonical expected external reference. For
Pi payment V1 these bytes are canonical txid bytes. Provider-native verification must
return the same reference or fail before verdict issuance.

No unverified Pi JSON schema is hard-coded in Lang core.

## PROTECTS AGAINST

- caller-selected provider finality state/reference/proof,
- raw provider response rebinding,
- verifier artifact substitution,
- caller-selected build-input/toolchain digests,
- one builder alone claiming reproducibility,
- one measured builder environment being counted twice,
- dropping reproducibility gate identity from finality provenance.

## DOES NOT PROTECT AGAINST

- malicious/buggy verifier semantics accepted by current policy,
- compromised toolchain or environment attestation authorities,
- two attacker-controlled but distinct attested environments,
- shared hypervisor/host compromise,
- false provider/network data accepted by verifier,
- measure-A/execute-B runtime TOCTOU,
- protected-key or host/runtime compromise.

## ASSUMPTIONS

- production environment measurements correspond to genuinely isolated builders,
- signed toolchain provenance refers to actual compiler bytes used,
- provider schema/version identity is pinned and reviewed,
- provider-native verifier performs real authenticated provider verification,
- final consumers validate the complete finality proof envelope.

## FAILURE MODE

Bootstrap HMAC environment attestation is not equivalent to hardware/cloud remote
attestation. If the environment attestation authority is compromised, two false
independent environments may be minted and the reproducibility independence claim fails.

## NEXT

1. Add provider-neutral hardware/cloud remote-attestation evidence interface.
2. Add revocation and epoch trust policy.
3. Close runtime load-handle TOCTOU.
4. Pin exact supported Pi backend/payment schema before a production parser.
5. Move durable replay/audit state into runtime custody.
