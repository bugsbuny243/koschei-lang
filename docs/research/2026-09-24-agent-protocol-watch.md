# Agent Protocol Watch — 2026-09-24

## Meaningful new signal: multi-vendor agent security architecture converges on runtime containment

On 2026-09-22, the Blueprint Alliance was announced by Okta together with AWS, CrowdStrike, Databricks, Docker, Google Cloud, Lovable, Proofpoint, Salesforce, ServiceNow, Wiz, and Zscaler. The group is developing an open, multi-vendor reference architecture for securing AI agents across identity, applications, data, infrastructure, and security boundaries.

Official announcement: https://investor.okta.com/news-and-events/news-releases/news-details/2026/Industry-Leaders-Form-the-Blueprint-Alliance-to-Advance-a-Shared-Architecture-for-Securing-AI-Agents/default.aspx

This is not an IETF/W3C protocol standard, but it is a meaningful provider-independent architecture signal because multiple major vendors explicitly converge on the same security properties:

- every agent is a first-class identity;
- access is scoped to the task instead of inherited as standing privilege;
- delegation remains traceable across agent handoffs;
- runtime behavior is continuously evaluated;
- containment/revocation must be rapid and reversible;
- governance must span vendor and trust boundaries.

The architecture separates four questions: where agents exist, what authority they have, what they are doing at runtime, and how the system responds. This reinforces that discovery, authorization, observation, and containment are separate security planes.

## Koschei Lang impact

The existing Lang separation remains correct, but `containment` should be treated as a first-class provider-independent primitive rather than merely a side effect of revocation.

```text
DISCOVERY != IDENTITY
IDENTITY != AUTHORITY
AUTHORITY != RUNTIME_BEHAVIOR
RUNTIME_BEHAVIOR != CONTAINMENT_DECISION
REVOCATION != CONTAINMENT
```

Candidate canonical primitive:

```text
ContainmentState {
  subject
  scope
  mode
  reason_evidence
  effective_at
  expires_at
  reversible
  issuer
  provenance
}
```

The important distinction is that authority can remain cryptographically valid while runtime evidence requires an immediate fence. Conversely, lifting a runtime fence must not silently restore authority that has separately expired or been revoked.

```text
VALID_AUTHORITY + UNSAFE_RUNTIME_STATE => FENCED

LIFT_CONTAINMENT
  MUST NOT
RESTORE_REVOKED_OR_EXPIRED_AUTHORITY
```

This extends the existing Koschei effect-boundary model:

```text
IdentityEvidence
  -> Authority
  -> DelegationChain
  -> RuntimeDecision
  -> ExecutionPermit
  -> EffectBoundary
  -> RuntimeEvidence
  -> ContainmentDecision
  -> ContainmentState
  -> Recovery/Reauthorization
```

## Interoperability implication

The alliance explicitly targets an open multi-vendor architecture. Koschei Lang therefore should not encode vendor-specific kill-switch, gateway, IAM, or agent-registration semantics in the core. Vendor controls should map into canonical operations such as:

```text
observe(subject)
evaluate(runtime_evidence)
fence(subject, scope)
suspend(authority_ref)
revoke(authority_ref)
restore(subject, conditions)
```

The core decides semantics; adapters perform enforcement in each provider environment.

## Other watched areas

No newer MCP specification release, A2A normative release, ERC-8004 revision, or DID/VC change found in this run that independently requires another Koschei Lang core primitive. A2A's current roadmap continues work on v1.1, bidirectional streaming, elicitation/multi-turn workflows, validation/TCK, and related robustness work, but those items do not supersede the provider-independent authority/evidence model already recorded.

A2A roadmap: https://a2a-protocol.org/latest/roadmap/

The W3C Verifiable Credentials Data Model v2.1 Working Draft dated 2026-09-13 remains relevant as a credential/evidence carrier, but it does not change the Lang rule that credential representation is separate from authority semantics.

W3C VC Data Model v2.1: https://www.w3.org/TR/vc-data-model-2.1/

## Status

Architecture impact: **meaningful**.

New canonical concern: **runtime containment as a security primitive independent of identity, authority, and revocation**.
