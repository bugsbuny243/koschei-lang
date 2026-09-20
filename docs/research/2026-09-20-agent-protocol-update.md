# Agent Protocol Update — 2026-09-20

Only meaningful architecture-affecting findings are recorded here.

## 1. IETF WIMSE adopts AIMS as a Working Group document

**Source:** IETF Datatracker — `draft-ietf-wimse-aims-00`, published/updated 2026-09-15.

The earlier AI Agent Authentication and Authorization draft has been replaced by the WIMSE Working Group document **AI Identity Management System (AIMS)**. This is materially stronger than an individual draft because the work is now on the WIMSE WG track.

AIMS explicitly models an AI agent as a workload and separates:

- stable agent identifier,
- cryptographically bound agent credentials,
- runtime credential provisioning,
- authentication,
- authorization,
- monitoring / observability / remediation,
- policy,
- compliance.

It also preserves the user/system context when an agent acts under delegated authority and treats that context as input to authorization and audit. The document recommends short-lived credentials, treats static API keys as an anti-pattern, and profiles existing WIMSE/SPIFFE/OAuth mechanisms rather than inventing a new provider-specific identity protocol.

### Koschei Lang impact

This reinforces the provider-independent split already used in the Lang security model:

```text
AgentIdentifier != AgentCredential
AgentCredential != Authentication
Authentication != Authorization
Authorization != Delegation
AuthorizationState != Observability
Observability != Remediation
```

AIMS also gives stronger support for a canonical runtime identity lifecycle:

```text
Principal
 -> StableIdentifier
 -> RuntimeCredential
 -> AuthenticationEvidence
 -> DelegatedAuthority
 -> RuntimeDecision
 -> ObservabilityEvidence
 -> RemediationTransition
```

The carrier remains replaceable. WIMSE ID, SPIFFE ID, X.509, WIT, JWT, OAuth Token Exchange and Transaction Tokens are adapters/carriers, not Koschei Lang core semantics.

New invariant to preserve:

```text
IDENTIFIER STABILITY != CREDENTIAL LONGEVITY
```

An agent can retain a stable identity while its cryptographic credentials are short-lived, rotated and audience-specific.

Another useful invariant:

```text
PRIMARY_IDENTITY_CREDENTIAL != RESOURCE_ACCESS_CREDENTIAL
```

Credential exchange may derive a narrowly targeted resource credential from the agent's primary workload identity without replacing the underlying identity.

## 2. HAPS: portable, action-bound human approval evidence

**Source:** iProov, Human Approval and Presence Specification (HAPS), published 2026-09-17 as an experimental open specification with reference implementation/test vectors.

HAPS targets a distinct gap: an agent may possess valid identity and delegated authority while the relying party still cannot prove that the human principal approved the **specific consequential action** now being requested.

The specification separates:

- machine-readable Action Intent,
- relying-party challenge,
- authoritative Signing View shown to the human,
- portable Consent Credential,
- freshness / expiry,
- recipient binding,
- single-use/replay protection.

It is proof-agnostic: biometric presence is one possible implementation, not a required security primitive. The relying party remains responsible for deciding which actions require approval and whether the approver has sufficient authority.

### Koschei Lang impact

Human approval should remain distinct from identity, delegation and execution permission:

```text
HUMAN_IDENTITY != HUMAN_APPROVAL
DELEGATED_AUTHORITY != SPECIFIC_ACTION_APPROVAL
APPROVAL != EXECUTION
```

Candidate provider-independent primitive:

```text
ApprovalEvidence {
    approver_ref
    action_digest
    presentation_digest
    relying_party
    challenge
    issued_at
    expires_at
    single_use_id
    proof
}
```

The important property is not the approval provider. It is cryptographic binding of approval to the exact action and authoritative representation the human reviewed.

Recommended state transition:

```text
ProposedAction
 -> ActionDigest
 -> ApprovalRequirement
 -> SigningViewCommitment
 -> ApprovalEvidence
 -> FreshRuntimeDecision
 -> ExecutionPermit
```

The old decision MUST be re-evaluated after approval. Approval evidence is an input to authorization, not a reusable `ALLOW` token.

New invariants:

```text
APPROVAL(action_A) MUST NOT AUTHORIZE action_B
APPROVAL MUST BE AUDIENCE-BOUND
APPROVAL MUST BE FRESH
APPROVAL MUST BE REPLAY-RESISTANT
APPROVAL_PROVIDER != APPROVAL_SEMANTICS
```

## Resulting Koschei direction

These two developments converge on a useful boundary:

```text
StableIdentity
 -> EphemeralCredential
 -> DelegatedAuthority
 -> ProposedAction
 -> ActionBoundHumanApproval? 
 -> RuntimeAuthorization
 -> ExecutionPermit
 -> ExternalEffect
 -> Evidence
 -> Remediation
```

Koschei Lang should continue to own these canonical semantics while WIMSE/SPIFFE/OAuth/DID/VC/MCP/A2A/ERC-style systems remain replaceable adapters or evidence carriers.

No additional MCP, A2A, DID/VC or ERC-8004-family change found in this scan was strong enough to justify another Lang-core primitive beyond the items above.
