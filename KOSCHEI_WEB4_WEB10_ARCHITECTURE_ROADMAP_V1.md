# KOSCHEI WEB4 → WEB10 ARCHITECTURE ROADMAP V1

Status: architecture roadmap; extends `KOSCHEI_LANG_ANA_VIZYON_RAPORU_2026-08-24.md` without replacing it.
Scope: Koschei Lang only. External Web3/Sentinel systems remain adapters/consumers, never Lang semantic authorities.

## Constitutional laws

1. `OBSERVABLE WORLD != CANONICAL WORLD`
2. `IDENTITY != AUTHORITY != REPUTATION != CAPABILITY`
3. `DISCOVERY != READ != LINK != EXECUTE != DELEGATE != REVEAL`
4. `CANONICAL CONTINUITY != REPRESENTATION CONTINUITY`
5. Compiler-derived privileged operation identity wins over runtime/adaptor claims.
6. External evidence may inform policy but never mints ambient authority.
7. Normalized Verified MIR facts are not re-derived from AST/source as a second authority.
8. Every horizon must fail closed when its canonical proof cannot be established.

## Horizon 4 — Sovereign / agentic execution

### Already present
- `vor` capability-first bounded authority.
- compiler-derived capability/effect identity.
- exact `CanonicalEffectRequest` and request-bound proof model.
- epoch/liveness Continuity model.
- single-use execution permit/receipt primitives.
- Khar/Galaxy final critical-effect admission.

### Missing canonical primitive
`DelegationAttenuationChainV1`.

Required proof law for every hop:

`child_authority ⊆ parent_authority`

The subset relation must cover capability/effect identity, canonical resource scope, subject scope, request binding and epoch interval. No hop may widen any dimension.

### Exit criteria
A coordinator → specialist → tool-executor chain can reach one exact privileged effect only when every delegation hop is provably attenuating and the leaf still passes ordinary Khar/Galaxy admission. Delegation itself is evidence, not a second authority.

---

## Horizon 5 — Portable identity / verifiable knowledge

### Already present
- Aevra canonical identity separated from visible representation.
- Nyr/Nur observer projection.
- provider-neutral external evidence/verifier contracts.
- trust-generation and attestation primitives.

### Missing
- explicit portable-identity adapter ABI that maps external identity claims into non-authoritative evidence.
- disclosure-minimization contract for selective identity attributes.
- revocation/freshness binding that cannot silently outlive Continuity.

### Exit criteria
DID/VC/workload identity or future identity systems can be consumed without importing their identifiers as Koschei authority or canonical subject identity.

---

## Horizon 6 — Intent-native computation

### Already present
- exact-request effect model.
- compiler-bound operation derivation.
- Source Intent → Verified IR provenance direction.

### Missing canonical primitive
`CanonicalIntentEnvelopeV1`.

It must bind intent digest, canonical subject scope, admissible effect/resource envelope, policy generation, compilation provenance and freshness without carrying an executable authority token.

### Core law
`INTENT != AUTHORITY`

An intent can be valid and still be denied execution.

### Exit criteria
The compiler/runtime can prove which exact intent produced an execution request while authority remains independently proven.

---

## Horizon 7 — Verifiable execution

### Already present
- Verified IR/build input primitives.
- deterministic/reproducible build direction.
- toolchain provenance.
- execution permit/receipt and canonical authority basis evidence.
- provider-neutral attestation verifier contracts.

### Missing
`ExecutionEvidenceGraphV1` joining:

`intent -> semantic seal -> Verified MIR -> transformation -> artifact -> payload -> execution permit -> attestation -> receipt`

Each edge must be independently checkable and typed. Missing edges fail verification rather than being inferred.

### Exit criteria
A verifier can establish that an observed execution belongs to one admitted intent/provenance chain without trusting filenames, mutable metadata or runtime assertions.

---

## Horizon 8 — Ephemeral / adaptive representation

### Already present
- Nyr rotating/non-faithful observer representation concepts.
- epoch/session/request-scoped reconstruction.
- opaque materialization handles.
- Continuity invalidation.

### Missing
`RepresentationEpochContractV1` and transformation proof binding.

Required law:

`same canonical semantics + different permitted epoch/session/build -> potentially different observer/execution representation`

while:

`authorized reconstruction -> deterministic verification of canonical equivalence`

Rotation must never alter authority, effects or program semantics.

### Exit criteria
Two authorized builds/sessions may expose materially different non-canonical representations while an independent verifier can prove semantic/provenance equivalence. Old representation knowledge must not itself authorize future reconstruction.

---

## Horizon 9 — Distributed trust / multi-realm computation

### Already present
- Galaxy/Khar constitutional admission.
- Sathra concurrence/failure-root independence concepts.
- trust anchors/generations.
- compartment and partial-revelation direction.

### Missing
- `ThresholdAuthorityProofV1` with explicit quorum/failure-domain semantics.
- `RealmCompartmentContractV1` for minimum revelation and cross-realm information flow.
- durable shared monotonic replay/finality state independent of one Python process.

### Core law
No single Infinity Stone, realm, observer, verifier or provider is a universal master credential.

### Exit criteria
A privileged distributed effect can require independent authority/evidence dimensions while compromise of one realm does not disclose or mint the complete canonical authority chain.

---

## Horizon 10 — Self-verifying computation universe

Horizon 10 is not a protocol version. It is the convergence target where Koschei can continuously prove the relationships among:

`intent + identity + authority + capability + Verified MIR + transformation provenance + execution evidence + observer policy + Continuity`

### Missing convergence primitive
`UniverseExecutionSealV1` — a non-authoritative cryptographic commitment over the accepted evidence graph and constitutional decision.

It must not contain a universal secret or become an execution credential. It is a verifiable receipt of an already-admitted reality.

### Exit criteria
For a privileged execution, Koschei can answer independently and fail-closed:
- what semantic intent was admitted?
- which canonical operation did the compiler derive?
- which attenuated authority chain permitted it?
- which Verified MIR and transformation produced the payload?
- which Continuity epoch was live?
- which runtime/attestation evidence witnessed execution?
- which observer projection was permitted to reveal what?

No answer may be reconstructed from a weaker observer representation when canonical evidence is absent.

---

# Implementation dependency order

The horizon numbers are research destinations, not implementation order. The actual dependency order is:

1. finish MIR semantic authority convergence and remove security-relevant AST fallback;
2. make normalized capability call-site identity the only privileged-operation identity input;
3. define canonical resource-scope subset semantics;
4. implement `DelegationAttenuationChainV1` as proof/evidence only;
5. bind delegation leaf to exact request/proof and Khar/Galaxy admission;
6. define `CanonicalIntentEnvelopeV1`;
7. build typed `ExecutionEvidenceGraphV1`;
8. bind representation epochs and transformation equivalence proofs;
9. move replay/finality/provenance custody into durable/native or independently isolated state;
10. add threshold/realm compartment contracts;
11. converge accepted evidence into non-authoritative `UniverseExecutionSealV1`;
12. only then add external Web4/Web5/agent/DID/VC/MCP/A2A/payment adapters.

## Stop rules

- no `web4`, `web5`, `web10`, `agent`, `wallet`, `chain`, provider or protocol keyword in Koschei core merely for branding;
- no external identity becomes authority;
- no payment/finality/reputation evidence becomes authority;
- no delegation proof bypasses leaf Khar/Galaxy admission;
- no representation rotation claim is treated as source secrecy;
- no AST/source fallback may reinterpret a fact already claimed canonical by Verified MIR;
- no new syntax before a real semantic gap is established;
- no horizon is marked implemented from documentation alone.

# Threat-model template for every horizon primitive

Every implementation PR must state:

## PROTECTS AGAINST
What attacker capability is reduced?

## DOES NOT PROTECT AGAINST
What remains possible?

## ASSUMPTIONS
Which compiler/runtime/cryptographic/hardware/distributed components are trusted?

## FAILURE MODE
What fails closed, and what happens if freshness, proof, provenance or custody cannot be verified?

# Current checkpoint

## SPEC STATE
Web4→Web10 is now decomposed into measurable semantic/security capabilities rather than version branding.

## COMPILER STATE
MIR convergence remains the immediate blocker before agentic/delegation semantics become canonical.

## RUNTIME STATE
The target remains sealed Verified MIR execution with capability-first constitutional admission and no source-AST execution authority.

## SECURITY MODEL
Future identity, agent, payment, attestation and representation systems are evidence/adapters unless Koschei's own canonical authority laws explicitly admit an action.

## EXPERIMENTAL
All named missing V1 primitives in this roadmap are design targets until implemented and adversarially tested.

## TESTED
This document makes no runtime PASS claim.

## NEXT
Close MIR authority convergence, then specify canonical resource-scope subset semantics as the prerequisite for delegation attenuation.
