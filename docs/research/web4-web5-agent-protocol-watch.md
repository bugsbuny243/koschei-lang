# Web4 / Web5 & Agent Protocol Watch

Provider-independent security research notes for Koschei Lang.

> Rule: external protocols and credential formats remain adapters/evidence carriers. They do not become authority semantics in the Lang core.

## 2026-09 — Consolidated findings

### Core architecture direction

The recurring standardization signal is convergence toward strict separation of identity, authority, capability, delegation, intent, runtime authorization, execution, evidence, trust, and audit.

```text
IDENTITY != AUTHORITY
DISCOVERY != IDENTITY
DISCOVERY != TRUST
DISCOVERY != CAPABILITY
DISCOVERED_CAPABILITY != GRANTED_CAPABILITY
CAPABILITY != EXECUTION_PERMISSION
INTENT != CAPABILITY
INTENT != EXECUTION_PERMISSION
ATTESTATION != AUTHORIZATION
PLATFORM_ATTESTATION != ACTION_AUTHORIZATION
DELEGATION_SIGNATURE != SENDER_BINDING
AUTHORIZED != EFFECTIVE
EXECUTION != SUCCESS
SUCCESS != TRUST
AUDIT_LOG != AUDIT_PROOF
SECURITY_SEMANTICS != CREDENTIAL_FORMAT
```

### Delegation / capability attenuation

Delegated authority must monotonically narrow. Candidate canonical constraint dimensions:

```text
resources
operations
arguments
magnitude/value
time/expiry
audience
delegation_depth
redelegation
context
```

Hard invariant:

```text
EffectiveAuthority(child) <= EffectiveAuthority(parent)
```

A child must never widen the parent's authority. Parent validity must also be evaluated at reliance/execution time rather than assuming historical validity is sufficient.

```text
VALID_CHILD_DELEGATION requires VALID_PARENT_NOW
was_valid(parent) != valid(parent, now)
```

### Carrier-independent identity and delegation

JWT, X.509, DID/VC and future credential representations should map into canonical Koschei objects instead of defining Lang semantics.

Candidate primitives:

```text
Principal
IdentityEvidence
PrincipalBinding
Authority
Capability
ConstraintSet
DelegationEvidence
DelegationChain
ProofOfPossession
ExecutorBinding
```

`DelegationProof` and `Holder/ExecutorProof` remain separate. A principal signing a delegation does not prove that the current request was produced by the authorized executor key.

### Discovery and interoperability

MCP/A2A/agent directories/Agent Cards are treated as discovery and interoperability surfaces, not authority sources.

```text
DiscoveryDescriptor {
  endpoint
  protocol
  advertised_capabilities
  descriptor_reference
}
```

`DiscoveryDescriptor` is explicitly non-authoritative.

External DID/VC, registry, KYA, ERC-8004 or ecosystem trust signals should enter as evidence:

```text
ExternalTrustEvidence {
  issuer
  subject
  claims
  scope
  validity
  provenance
}
```

Local authorization remains a Koschei decision.

### Runtime authorization state

Authorization is time-evolving state rather than a permanent property of a credential.

```text
Intent
 -> DelegationChain
 -> AuthorizationState[n]
 -> AuthorizationTransition[n -> n+1]
 -> ProposedAction
 -> RuntimeDecision
 -> ExecutionPermit
```

A useful decision model is:

```text
Decision = ALLOW | DENY | PENDING(requirements[])
```

Possible requirements include human approval, second attestation, budget reservation, or fresh identity proof. Satisfying a prerequisite triggers fresh policy evaluation rather than reusing a stale `ALLOW`.

### Action binding and consumable capabilities

Authorization should bind to the concrete proposed action. Single-use execution credentials/nullifiers are modeled independently from authority itself.

Candidate primitives:

```text
ActionCommitment
ActionDigest
ExecutionPermit
ExecutionNullifier
ConsumptionProof
```

Important distinction:

```text
AUTHORIZATION_SOUNDNESS != CAPABILITY_CONSUMPTION
```

At-most-once consumption does not establish that the action was correctly authorized.

### Acceptance criteria and outcome evidence

For consequential agent actions, acceptance/evidence obligations should be committed before execution rather than invented after observing the result.

```text
criteria_commit < evidence_creation < outcome_attestation
```

Candidate primitives:

```text
AcceptanceCriteria
EvidenceObligation
OutcomeAttestation
EvidenceBundle
```

### Execution environment vs action authorization

TEE/TPM/GPU/RATS/workload attestation can provide execution-environment evidence, but must never automatically produce execution authority.

```text
ExecutionEnvironmentEvidence != ExecutionPermit
```

### Effect boundary

An authorized action is not necessarily externally effective yet.

```text
EffectState =
  PROPOSED
  | AUTHORIZED
  | EFFECTIVE
  | FENCED
```

This creates a final security boundary where revocation, approval withdrawal, runtime risk or policy changes can still prevent an external effect.

### Revocation and evidence history

Authority state is mutable; execution history is append-only.

```text
REVOKE(AUTHORITY) blocks FUTURE_EXECUTION
REVOKE(AUTHORITY) MUST NOT erase PAST_EVIDENCE
```

Canonical rule:

```text
AUTHORITY STATE IS MUTABLE;
EXECUTION HISTORY IS APPEND-ONLY.
```

### Verifiable action / audit graph

The target is not merely logging but cryptographically linking intent, delegation, authorization state, action, execution and evidence.

```text
Intent
 -> AuthorityMandate
 -> DelegationChain
 -> CurrentAuthorityState
 -> ActionCommitment
 -> RuntimeDecision
 -> ExecutionPermit
 -> EffectBoundary
 -> ExecutionReceipt
 -> OutcomeEvidence
 -> ImmutableEvidenceHistory
```

For cross-organization actions, bilateral evidence may be represented independently of any particular protocol:

```text
BilateralActionEvidence {
  proposal_commitment
  requester_attestation
  performer_attestation
  constraint_result
  disposition
  mutual_acknowledgement
}
```

### Recourse / remediation

Execution success and authorization do not establish what happens when an action is disputed, quarantined, rolled back, suspended or escalated.

Candidate primitive:

```text
ActionRecourse {
  action_digest
  authorization_ref
  procedure_commitment
  handler_binding
  validity_window
  trigger_policy
  effect_policy
  provenance
}
```

Invariant:

```text
POST_ACTION_POLICY MUST NOT RETROACTIVELY MODIFY PRE_ACTION_COMMITMENTS
```

### Private reasoning

Private model reasoning is not an authority primitive. Cryptographic commitment to private material proves correspondence to committed bytes, not truth of the underlying claim.

```text
PRIVATE_REASONING != AUTHORITY_EVIDENCE
COMMITMENT_PROOF != TRUTH_PROOF
```

### Candidate Koschei Lang canonical security graph

```text
Principal
  -> IdentityEvidence

Intent
  -> IntentCommitment

Authority
  -> Capability
    -> ConstraintSet
      -> DelegationChain

AuthorizationState
  -> AuthorizationTransition

ProposedAction
  -> ActionDigest
  -> RuntimeDecision
    -> Requirements
    -> ExecutionPermit

Execution
  -> EffectBoundary
  -> ConsumptionProof
  -> ExecutionReceipt
  -> OutcomeEvidence
  -> AuditGraph
  -> RecourseBinding
```

### Adapter boundary

External standards remain adapters/carriers:

```text
MCP / A2A        -> transport, discovery, interoperability adapters
DID / VC / X.509 / JWT -> identity and evidence carriers
ERC-8004-like registries -> identity/reputation/validation evidence
OAuth / AuthZEN -> authorization interoperability adapters
RATS / TEE / TPM -> execution-environment evidence adapters
ERC attestations -> action/evidence adapters
```

Koschei Lang owns the canonical security semantics and must not depend on any one provider, registry, blockchain, credential format, agent framework, model vendor or transport protocol.

---

Future meaningful Web4/Web5 and agent-protocol findings should be appended to this file as dated entries. Repeated announcements that do not alter the provider-independent security model should not be added.


## 2026-10-02 — Post-quantum durability of agent identity/delegation evidence

### New signal

A new IETF Internet-Draft published 28 September 2026, `draft-uppalapati-wimse-pq-agent-identity-00`, focuses specifically on post-quantum requirements for software and AI-agent identity. The architecturally important point for Koschei Lang is not a new credential carrier: it is the distinction between verifying a delegation **now** and preserving the ability to verify historical delegation evidence **years later** after signing algorithms or keys have weakened or been retired.

The draft argues that an archived delegation signature proves who signed, not when it was signed. Long-lived evidence therefore needs trusted-time anchoring plus renewal/re-anchoring before the cryptographic protection becomes weak. A timestamp anchor is itself cryptographically protected, so long-term evidence durability must account for the security of the anchor rather than treating a timestamp as timeless truth.

### Koschei Lang primitive impact

Add a provider-independent long-term evidence layer rather than embedding post-quantum policy into DID, VC, JWT, X.509, MCP, A2A, ERC-8004, or any one signature suite.

Candidate primitives:

```text
EvidenceTimeAnchor
CryptoProtectionEpoch
EvidenceRenewal
VerificationHorizon
AlgorithmSecurityState
LongTermVerificationProof
```

Required separations:

```text
SIGNATURE_VALID_NOW != EVIDENCE_VERIFIABLE_LATER
SIGNER_IDENTITY != TRUSTED_SIGNING_TIME
TIMESTAMP_PRESENT != TIMESTAMP_DURABLE
CREDENTIAL_FORMAT != CRYPTOGRAPHIC_LONGEVITY_POLICY
KEY_ROTATION != EVIDENCE_RENEWAL
```

Candidate evidence lifecycle:

```text
DelegationEvidence
  -> SignatureVerification
  -> EvidenceTimeAnchor
  -> CryptoProtectionEpoch
  -> EvidenceRenewal[n]
  -> LongTermVerificationProof
```

Provider-independent invariant:

```text
PAST_EVIDENCE MUST REMAIN VERIFIABLE
WITHOUT REQUIRING THE ORIGINAL SIGNATURE ALGORITHM
TO REMAIN SECURE FOREVER.
```

This extends the existing Koschei rule that authority state is mutable while execution history is append-only: append-only history is insufficient if its cryptographic evidence becomes unverifiable over time.

### Status / caution

This is an individual Informational Internet-Draft, not an adopted IETF standard. Treat it as an emerging architecture signal. The useful Lang change is the generic separation of current authorization validity from long-term evidentiary durability; the draft's particular cryptographic profiles should remain adapter/policy choices.

Source: IETF, `draft-uppalapati-wimse-pq-agent-identity-00`, published 2026-09-28.
