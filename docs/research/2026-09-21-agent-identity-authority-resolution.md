# Agent Identity / Authority Resolution Watch — 2026-09-21

## Meaningful new developments

### 1. Agent Trust Profile — 16 September 2026

IETF Internet-Draft `draft-mnki-agent-trust-profile-00` profiles existing standards rather than inventing a new credential system. It combines JWS, OAuth/OIDC, SPIFFE/WIMSE workload identity, DPoP-style proof of possession, OpenID AuthZEN and OpenID Federation to express agent identity, principal binding, attenuated delegation, constrained capabilities, request proof-of-possession, authorization attestations, provenance, revocation and cross-organization trust.

Status: Informational Internet-Draft; not an RFC or adopted standard.

Source: https://www.ietf.org/ietf-ftp/internet-drafts/draft-mnki-agent-trust-profile-00.html

#### Koschei Lang impact

```text
CREDENTIAL_VALIDITY != CURRENT_AUTHORITY
AGENT_IDENTITY != PRINCIPAL_BINDING
PRINCIPAL_BINDING != DELEGATED_AUTHORITY
DELEGATED_AUTHORITY != REQUEST_PROOF_OF_POSSESSION
```

Canonical verification remains provider-independent:

```text
IdentityEvidence
 -> PrincipalBinding
 -> DelegationChain
 -> ConstraintSet
 -> CurrentAuthorityState
 -> ExecutorProof
 -> RuntimeDecision
```

### 2. AIN-WRP authoritative pre-interaction resolution — 18 September 2026

IETF Internet-Draft `draft-tanase-ain-authoritative-resolution-00` introduces protocol-independent authoritative resolution of persistent digital-agent identities before protected interaction. Its model explicitly separates a stable identity lookup anchor from credentials, proof of control, delegated authority, operational eligibility, policy decision and execution. Resolution can expose current lifecycle/operator/authority/endpoint/mandate/restriction/provenance/verification information from sources competent to assert each item.

Status: Standards Track individual submission; not an RFC and not evidence of IETF Working Group adoption.

Source: https://www.ietf.org/ietf-ftp/internet-drafts/draft-tanase-ain-authoritative-resolution-00.html

#### Koschei Lang impact

This adds a useful distinction: persistent identity resolution and current operational eligibility are different security questions.

```text
PERSISTENT_IDENTITY != CREDENTIAL
IDENTITY_RESOLUTION != PROOF_OF_CONTROL
IDENTITY_RESOLUTION != AUTHORITY
AUTHORITY != OPERATIONAL_ELIGIBILITY
OPERATIONAL_ELIGIBILITY != POLICY_DECISION
POLICY_DECISION != EXECUTION
```

Candidate provider-independent primitives:

```text
PersistentIdentityRef
ResolutionEvidence
LifecycleState
OperatorBinding
OperationalEligibility
```

`PersistentIdentityRef` MUST NOT implicitly grant authority. `ResolutionEvidence` should be freshness-bound and provenance-aware because lifecycle, restrictions, operator binding and mandate state may change independently of the stable identifier.

```text
STABLE_IDENTIFIER MUST NOT IMPLY STABLE_AUTHORITY
CURRENT_OPERATIONAL_ELIGIBILITY requires FRESH_STATE_EVIDENCE
```

### Combined architecture consequence

```text
PersistentIdentityRef
 -> ResolutionEvidence
 -> IdentityEvidence
 -> PrincipalBinding
 -> DelegationChain
 -> CurrentAuthorityState
 -> OperationalEligibility
 -> ExecutorProof
 -> ProposedAction
 -> RuntimeDecision
 -> ExecutionPermit
```

The important new layer is **current operational eligibility**. An agent can have a valid persistent identity and valid delegated authority while still being ineligible to operate because of lifecycle state, restriction, suspension, endpoint state or other fresh authoritative information.

## Other watched lines

No newer MCP/A2A, DID/VC or ERC-8004 change found in this scan materially alters the canonical provider-independent security model beyond the distinctions above. Protocol-specific developments remain adapter-layer concerns unless they introduce a new security invariant.
