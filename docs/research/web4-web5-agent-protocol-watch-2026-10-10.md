# Web4/Web5 and Agent Protocol Watch — 2026-10-10

Scope: provider-independent agent identity, delegation, authorization, verifiable actions, MCP/A2A, and Web agent accountability. Research only; no runtime or architecture changes.

## 1. Agent Delegation Receipts -11 (published 2026-10-09) — high relevance

Source: https://datatracker.ietf.org/doc/draft-nelson-agent-delegation-receipts/11/

Substantive changes:
- Replaces custom, JavaScript insertion-order JSON signing with RFC 8785 JCS canonicalization plus RFC 7515 JWS as primary format; RFC 9052 COSE_Sign1 is an alternative for constrained runtimes. Pre-11 artifacts are **not** verifiable under the new profiles without legacy handling.
- Formalizes monotonic attenuation of structured scopes across delegation chains, depth limits, parent receipt linkage, cascade revocation, and one-time-use receipts backed by a durable shared consumption store.
- Explicitly requires fail-closed treatment for receipts marked revocationRequired when the registry is unreachable, and when a parent in the chain requires a live check.
- Explicitly documents limitations: the reference verifier is in the operator-controlled process and can be bypassed by a malicious operator; revocation distribution remains unsolved; its RFC 3161 timestamp handling checks digest presence rather than validating the TSA signature/chain; some runtime measurements are self-attested. A signed receipt is evidence, not enforcement.

Koschei architecture implications:
- Keep `CanonicalReceiptBody`, `ReceiptWireProfile` (JWS/COSE), `SignatureVerificationEvidence`, and `AuthorityDecision` distinct. Cryptographic serialization is an adapter, not the authority model.
- Model `DelegationAttenuationProof`, `AncestorRevocationStatus`, `RevocationFreshnessRequirement`, and `GlobalConsumptionRecord` with fail-closed high-consequence enforcement.
- Keep `TimestampPresence` distinct from `TrustedTimestampVerification`, and `AuditReceipt` distinct from `ExecutionGate`.
- Security invariants: `SIGNED_RECEIPT != ENFORCED_POLICY`; `DIGEST_PRESENT != TRUSTED_TIMESTAMP`; `OFFLINE_UNKNOWN != NOT_REVOKED`; `ONE_TIME_TOKEN != AT_MOST_ONCE_WITHOUT_SHARED_STATE`.

Status: individual IETF Internet-Draft, intended Informational, **not an adopted IETF standard**.

## 2. Universal Crawler Accountability Protocol (UCAP) -00 (published 2026-10-09) — adjacent relevance

Source: https://datatracker.ietf.org/doc/draft-neve-ucap-00/

- Proposes request-level `Crawler-Request-ID` bound to the HTTP method, authority, target URI, and operator identity via RFC 9421 HTTP Message Signatures / Web Bot Auth; a UUID or User-Agent alone is not identity evidence.
- Separates authenticated operator recognition of a request from its legitimacy or authorization; supports operator-hosted request verification, origin-scoped abuse case status, and domain-scoped future exclusion requests.
- Explicitly says a valid UCAP ID is **not** resource-access authorization. Exclusion is a request to a cooperating operator, not network-level enforcement. Privacy and working-group scope are unresolved.

Koschei architecture implications:
- Consider `RequestProvenanceEvidence`, `OperatorIdentityBinding`, `OriginScopedRecourse`, and `ExclusionAcknowledgment` as evidence/recourse adapters rather than authorization grants.
- Invariants: `REQUEST_CORRELATION != AUTHENTICATION`; `AUTHENTICATED_REQUEST != AUTHORIZED_REQUEST`; `OPERATOR_ACKNOWLEDGMENT != ENFORCED_EXCLUSION`.

Status: individual IETF Internet-Draft, intended Standards Track, **not an adopted IETF standard**.

## Decision

Track the drafts as interoperability signals. Do not import draft-specific JWS/COSE/HTTP fields into Koschei's provider-independent security core; define typed evidence, authorization state, revocation, and effect-boundary semantics independently. Validate any future implementation against the final published specification and threat model.
