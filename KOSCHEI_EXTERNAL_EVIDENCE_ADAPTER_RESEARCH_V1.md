# KOSCHEI EXTERNAL EVIDENCE ADAPTER RESEARCH V1

Status: research/specification input only; not canonical authority and not runtime implementation.
Scope: Koschei Lang only.
Date: 2026-09-07.

## Constitutional boundary

External protocols, credentials, conformance scores, discovery documents and confidence claims are evidence inputs. They do not mint Koschei authority.

The following laws remain unchanged:

`IDENTITY != AUTHORITY != REPUTATION != CAPABILITY`

`DISCOVERY != READ != LINK != EXECUTE != DELEGATE != REVEAL`

`EXTERNAL EVIDENCE != EXECUTION AUTHORITY`

Compiler-derived privileged operation identity, canonical resource scope, Continuity and Khar/Galaxy admission remain authoritative.

---

## 1. ConfidenceEvidenceAdapterABI — research target

### Motivation

W3C Verifiable Credential Confidence Methods introduces confidence methods and assurance-level information that can help a verifier evaluate how strongly a credential claim or presenter relationship should be trusted.

Koschei must consume such material only as external evidence.

### Proposed normalized evidence shape

A provider-neutral `ConfidenceEvidenceV1` should be able to bind:

- evidence source / scheme identifier;
- subject-claim digest rather than unrestricted raw identity data where possible;
- confidence/assurance method identifier;
- issuer/verifier identity evidence;
- verification outcome;
- evidence freshness / valid interval;
- evidence/proof digest;
- policy-generation binding;
- privacy/disclosure classification;
- adapter provenance.

It MUST NOT contain a Koschei capability token or execution permit.

### Evaluation pipeline

`external credential/confidence material`
`-> adapter validation`
`-> ConfidenceEvidenceV1`
`-> evidence freshness/revocation checks`
`-> policy evaluation`
`-> ALLOW/DENY/CONTAIN candidate input`
`-> ordinary canonical Khar/Galaxy authority admission`

A policy may reject, ignore or weight confidence evidence. Evidence alone cannot authorize execution.

### PROTECTS AGAINST

- importing an issuer confidence statement as ambient authority;
- confusing credential validity with Koschei execution permission;
- provider-specific confidence formats becoming core semantic authority;
- stale confidence evidence silently surviving without freshness checks.

### DOES NOT PROTECT AGAINST

- a dishonest or compromised issuer/verifier;
- compromised adapter implementation;
- incorrect assurance methodology at the external provider;
- privacy leakage before evidence reaches the Koschei boundary.

### ASSUMPTIONS

- cryptographic verification, when claimed, is performed by an appropriate verifier;
- policy generations are versioned and auditable;
- external identifiers remain evidence identifiers, not Aevra authority identities.

### FAILURE MODE

Unknown method, invalid proof, missing freshness, unsupported assurance semantics or ambiguous subject binding fails the evidence adapter closed. The runtime does not infer authority from partially verified material.

---

## 2. AgentConformanceEvidence — research target

### Motivation

Provider-independent agent conformance and benchmarking can produce reproducible test results, versioned benchmark corpora and comparable reports.

Koschei can use such results as evidence about observed behavior or claimed protocol conformance, not as authority.

### Proposed normalized evidence shape

`AgentConformanceEvidenceV1` may bind:

- conformance suite identifier + version;
- benchmark corpus identifier + digest;
- tested software/agent artifact identity or provenance digest;
- test environment provenance;
- individual check outcomes;
- score/result distribution context;
- reproduction evidence from independent parties when available;
- timestamp/epoch/freshness;
- signer/reporter evidence;
- adapter provenance.

### Core law

`CONFORMANCE CLAIM != AUTHORITY`

Passing a benchmark cannot produce `vor` authority, an execution permit, a canonical capability or a delegation grant.

### Horizon 7 relationship

When `ExecutionEvidenceGraphV1` exists, conformance evidence may attach as a typed external-evidence node. It may help a policy reason about risk, but it cannot replace:

- Verified MIR provenance;
- exact execution permit;
- runtime attestation;
- execution receipt;
- Khar/Galaxy admission.

### PROTECTS AGAINST

- vendor self-asserted conformance being treated as trusted execution authority;
- opaque scores with no corpus/version provenance;
- benchmark results silently applying to a different binary/build/agent artifact.

### DOES NOT PROTECT AGAINST

- weak benchmark design;
- gaming the benchmark;
- distribution shift between test and production;
- compromised conformance infrastructure.

### ASSUMPTIONS

- conformance suites and corpora are version-addressed;
- artifact identity can be bound to the tested implementation;
- policy treats evidence weight separately from authority.

### FAILURE MODE

Missing suite version, artifact binding, corpus digest or reproducibility provenance makes the evidence non-admissible for policy use. Execution does not fail merely because external conformance evidence is absent unless a specific Koschei policy explicitly requires it.

---

## 3. DiscoveryClaim != ExecutionAuthority — adapter invariant

### Motivation

A2A Agent Cards, MCP discovery/list operations and future protocol equivalents can advertise identity, endpoints, skills/tools and capabilities.

Koschei must interpret all such material as discovery claims.

### Canonical invariant

`DISCOVERY CLAIM != CANONICAL CAPABILITY`

`DECLARED SKILL != EXECUTION PERMIT`

`AGENT CARD != DELEGATION PROOF`

`TOOL LISTING != AUTHORITY`

### Adapter flow

`A2A/MCP/future protocol discovery document`
`-> syntax/protocol validation`
`-> provider-neutral DiscoveryClaimEvidenceV1`
`-> optional policy filtering`
`-> canonical resource/operation resolution`
`-> independent DelegationAttenuationChainV1 proof if delegation is required`
`-> exact request binding`
`-> Khar/Galaxy admission`

No discovery adapter can supply `child_authority ⊆ parent_authority` merely because a remote agent claims a capability.

### Stateless MCP consequence

A self-describing request carrying protocol version, client identity or client capabilities is still transport/request metadata. It cannot become Koschei canonical identity or authority without independent admission.

Explicit cross-call handles similarly remain opaque application evidence/state references unless Koschei has a canonical contract for them.

### A2A consequence

Agent Cards may help identify endpoints, advertised skills and metadata. Signed metadata can improve integrity/authenticity evidence, but it cannot mint a Koschei capability, delegation grant or exact execution permit.

### PROTECTS AGAINST

- capability confusion between protocol advertisement and canonical authority;
- discovery poisoning becoming direct execution privilege;
- signed metadata being mistaken for authorization;
- stateless request metadata being elevated into ambient identity/authority.

### DOES NOT PROTECT AGAINST

- compromised external protocol endpoints;
- malicious but correctly signed discovery documents;
- incorrect local policy mapping;
- compromised Koschei adapter/runtime TCB.

### ASSUMPTIONS

- adapters are provider-neutral and narrow;
- canonical operation/resource mapping is deterministic;
- delegation proof and execution admission are independent from discovery parsing.

### FAILURE MODE

Unknown or conflicting discovery claims are non-authoritative and ignored/rejected. They never trigger fallback to guessed capability or runtime-selected authority.

---

# Architectural placement

These research targets belong outside Lang core syntax:

`external protocol / credential / benchmark`
`-> provider-specific parser/verifier adapter`
`-> provider-neutral Koschei evidence object`
`-> evidence policy`
`-> canonical request/authority pipeline`

There will be no `mcp`, `a2a`, `vc`, `did`, `agentCard` or provider keyword added to the language core merely to support these systems.

# Dependency order

1. finish MIR semantic authority convergence;
2. define canonical resource-scope subset semantics;
3. implement `DelegationAttenuationChainV1`;
4. implement typed external-evidence envelope/common ABI;
5. add `ConfidenceEvidenceV1` adapter contract;
6. add `AgentConformanceEvidenceV1` contract;
7. add `DiscoveryClaimEvidenceV1` contract;
8. attach admissible evidence nodes to `ExecutionEvidenceGraphV1`;
9. only then implement protocol/provider-specific adapters.

# Current status

## SPEC STATE
Three external-evidence research gaps are now defined without changing Koschei authority semantics.

## COMPILER STATE
No compiler behavior changes.

## RUNTIME STATE
No runtime behavior changes.

## SECURITY MODEL
External confidence, conformance, discovery and signed metadata remain policy evidence only.

## EXPERIMENTAL
`ConfidenceEvidenceV1`, `AgentConformanceEvidenceV1`, `DiscoveryClaimEvidenceV1` and their adapter ABIs are research targets, not implemented features.

## TESTED
Documentation/research only; no runtime PASS claim.

## NEXT
After MIR convergence and resource-scope subset semantics, define one provider-neutral external-evidence envelope before adding any protocol-specific adapter.
