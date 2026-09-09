# KOSCHEI LANG — AGENTIC WEB READINESS V1

Status: **research/specification bridge — non-canonical until implementation + adversarial validation**

Date: 2026-09-06

Scope: **Koschei Lang only.** This document does not move Web3 product logic or Sentinel logic into Lang. External agent networks, identity systems, payment rails, blockchains, MCP/A2A transports, DID providers and verifier providers remain adapters or external systems.

## 1. Why this exists

The labels "Web4" and "Web5" are not one settled standards stack. In 2026, multiple incompatible projects and Internet-Drafts use "Web4" for an agentic/verifiable/sovereign web direction. The useful common technical direction is narrower:

- autonomous software agents become first-class network actors;
- actors need portable/verifiable identity;
- authority must be delegated with scope attenuation rather than ambient credentials;
- actions need exact commitments and independently checkable provenance;
- validity becomes time/epoch scoped;
- external evidence, reputation or payment must not automatically become authority;
- observer-visible identity should not have to equal canonical execution identity.

The older Block/TBD "Web5" umbrella is no longer a single active product authority. Its decentralized-identity components were contributed to the Decentralized Identity Foundation. Therefore Koschei must not depend on the Web4/Web5 brand names. It should expose provider-neutral semantics that remain useful if those labels disappear.

## 2. External signals considered

This research is informed by current public work including:

- IETF individual Internet-Drafts describing Web4 as agentic/verifiable/federated/sovereign-entity capable;
- ERC-8004 identity, reputation and validation registries for agents;
- AgentID-style proposals carrying identity, capability and delegation-chain claims;
- MCP/A2A-style agent/tool interaction transports;
- x402-style machine payment rails;
- DID / Verifiable Credential / Decentralized Web Node work moved from Block/TBD into DIF.

Important: an Internet-Draft is not an IETF standard merely because it is hosted by IETF. Koschei must treat these as design signals, not constitutional dependencies.

## 3. Koschei already has the right native direction

The existing Koschei architecture already covers much of the security substrate without copying these protocols:

- **Aevra**: canonical entity identity independent from visible bytes.
- **vor**: bounded authority/capability semantics.
- **Continuity / epoch**: shared liveness and expiry boundary.
- **CompilerCapabilityEffectBasisV1**: privileged operation identity derived from compiler semantics rather than runtime caller choice.
- **CanonicalEffectRequest**: exact privileged action identity.
- **RequestBoundProof**: proof bound to one exact request.
- **CanonicalAuthorityBasisV1**: evidence of the existing Koschei enforcement result; never ambient authority.
- **ExecutionPermitV1**: exact-request, exact-operation, epoch-bound, single-use permit.
- **Toolchain / Verified IR / reproducible build provenance**: artifact lineage and verifier trust primitives.
- **Nyr / Nur**: observer projection separated from canonical identity/authority.
- **Khar / Galaxy admission**: constitutional critical-effect enforcement remains the final authority.

Therefore the goal is not to add `web4`, `agent`, `did`, `wallet`, `pay` or other fashion keywords to the language.

## 4. Newly identified semantic gap

### Delegation attenuation is not yet a first-class canonical proof

Agentic systems routinely require chains such as:

```text
human / service principal
-> coordinator agent
-> specialist agent
-> tool executor
-> one exact privileged effect
```

Koschei already has scoped exact-request authority at the leaf, but the canonical model does not yet make a multi-hop delegation chain itself a normalized proof object whose central invariant is:

> **Every delegation hop may preserve or reduce authority, never widen it.**

A downstream agent must not gain a capability, resource scope, effect, epoch, identity horizon or request freedom that its parent did not possess.

This is a real semantic gap, not a reason for a new syntax family.

## 5. Proposed primitive — DelegationAttenuationChainV1

This is a semantic design target, not yet an implementation claim.

Each hop should bind at minimum:

- parent delegation digest;
- issuer canonical subject-scope digest;
- delegate canonical subject-scope digest;
- compiler-derived capability/effect identity;
- permitted resource/target scope digest;
- request-binding mode;
- earliest valid epoch;
- latest valid epoch;
- one delegation nonce / replay identity;
- attenuation proof digest;
- chain root digest.

A hop is valid only if all of the following hold:

1. **No capability widening** — child capability/effect is equal to or a strict subset of the parent authority domain.
2. **No resource widening** — child target/resource scope is equal to or narrower than parent scope.
3. **No temporal widening** — child validity interval is contained inside the parent interval.
4. **No identity escape** — child Hara/subject horizon is allowed by the parent delegation relation.
5. **No request widening** — an exact-request parent cannot delegate a wildcard request.
6. **No replay authority** — a consumed single-use leaf cannot be re-materialized as a fresh child delegation.
7. **No observer authority** — Nyr/DID/public agent identifier is not itself sufficient to mint canonical delegation.
8. **No external-evidence authority** — reputation, payment, VC, registry state or provider attestations may contribute evidence but cannot replace Khar/Galaxy admission.
9. **Compiler identity wins** — after a privileged capability call identity is known from normalized MIR, a runtime agent or adapter may not substitute capability type/method/effect.
10. **Leaf execution remains constitutional** — a valid delegation chain is necessary evidence for delegated execution, not an ALLOW decision by itself.

## 6. Intended canonical path

```text
source intent
-> normalized Verified MIR capability identity
-> canonical effect identity
-> root vor authority
-> DelegationAttenuationChainV1
   -> hop 0 scope
   -> hop 1 narrower/equal scope
   -> ...
   -> leaf exact-request scope
-> CanonicalEffectRequest
-> RequestBoundProof
-> existing reconstruction/materialization boundaries
-> existing Khar/Galaxy admission
-> single-use execution permit / consumption
-> effect receipt / provenance
```

There must not be a parallel "agent authority" gate beside the existing Koschei authority physics.

## 7. External protocol adapter rule

Koschei Lang core should be able to map external protocols into observer/evidence adapters without adopting their authority model.

Examples:

- DID / ERC-8004 identity -> candidate external identity evidence; canonical identity remains Aevra.
- MCP/A2A advertised tool/capability -> discovery metadata; canonical callable authority remains compiler/capability/Khar derived.
- x402 payment -> settlement evidence; payment success does not imply execution authority.
- external reputation -> policy input/evidence; reputation does not mint vor.
- VC / attestation -> evidence with provenance; claim is not `shi` until verified under admitted trust roots.

## 8. Relationship to OBSERVABLE WORLD != CANONICAL WORLD

Agentic systems increase the value of Koschei's dual-world model.

An external network may observe:

- rotating agent alias;
- DID or registry handle;
- protocol endpoint;
- bounded capability advertisement;
- request commitment;
- attestation/proof envelope.

It should not automatically reveal:

- stable canonical Aevra identity;
- full internal capability graph;
- reusable canonical execution handles;
- hidden resource topology;
- complete MIR/semantic structure;
- future epoch mappings.

This reduces durable correlation and reusable knowledge. It does not make canonical state impossible to recover under a fully compromised trusted runtime.

## 9. Threat model

### PROTECTS AGAINST

If implemented correctly, delegation attenuation can protect against:

- a child agent silently widening delegated privileges;
- wildcard authority appearing after an exact-request delegation;
- stale child authority surviving beyond the parent epoch window;
- runtime adapters substituting a stronger capability than compiler identity;
- external identity/reputation/payment systems becoming ambient Koschei authority;
- one delegation receipt being rebound to another request/resource/subject;
- observer-facing aliases being treated as canonical execution credentials.

### DOES NOT PROTECT AGAINST

It does not by itself protect against:

- compromised compiler/runtime/TCB that lies about canonical semantics;
- stolen root capability or signing/HMAC keys;
- a malicious parent legitimately delegating everything it is permitted to delegate;
- side-channel leakage, debugger capture, memory scraping or hardware compromise;
- malicious external identity/reputation/attestation providers that are trusted incorrectly;
- semantic bugs in resource-scope subset comparison;
- rollback unless replay/epoch state is actually durable and independently protected.

### ASSUMPTIONS

- normalized MIR capability identity is trustworthy and unambiguous;
- capability/resource subset relations have deterministic canonical encodings;
- Continuity epoch truth is shared and fail-closed;
- root authority was admitted through existing Koschei constitutional rules;
- cryptographic keys and trust roots are separated by role;
- replay/consumption state is durable enough for the deployment threat model.

### FAILURE MODE

Fail closed if:

- a parent hop is missing or malformed;
- a child scope cannot be proven to be a subset;
- capability identity is ambiguous;
- resource scope comparison is unknown;
- epoch state cannot be read;
- chain digest or request binding mismatches;
- an external adapter attempts to become authority;
- a delegation chain conflicts with compiler-derived capability identity.

## 10. Implementation order

Do not derail the current core convergence work.

1. Finish normalized MIR capability call-site authority and remove relevant AST fallback authority.
2. Reuse the normalized capability identity as the only privileged-operation identity input.
3. Define canonical resource-scope subset semantics.
4. Implement `DelegationAttenuationChainV1` as proof/evidence, not a second authority system.
5. Bind the leaf to the existing exact `CanonicalEffectRequest` / `RequestBoundProof` path.
6. Add adversarial tests for capability/resource/epoch/request widening and replay.
7. Bind chain/provenance digests into execution receipts.
8. Only then add external DID/ERC-8004/MCP/A2A/x402 adapters if a real integration requires them.

## 11. Required tests before canonical admission

- child cannot add a capability/effect;
- child cannot cross a power domain;
- child cannot widen resource scope;
- child cannot widen epoch interval;
- exact-request parent cannot become wildcard child;
- chain cannot be reordered or splice hops from another root;
- leaf request digest mismatch fails closed;
- leaf compiler capability identity mismatch fails closed;
- Nyr/external DID identity cannot mint canonical delegation;
- payment/reputation/VC/attestation alone cannot mint authority;
- consumed single-use leaf cannot be replayed;
- tampering any hop changes chain digest and rejects;
- unknown subset relation fails closed;
- external adapter removal does not change canonical Koschei semantics.

## 12. Decision

**Koschei Lang should prepare for the agentic/verifiable web, but it should not become a "Web4 language" or "Web5 language".**

The durable opportunity is to make Koschei a language/runtime where autonomous actors can operate through compiler-bound, attenuating, exact-request, time-scoped capabilities with verifiable provenance while the observer-visible world remains deliberately distinct from canonical execution reality.

That direction extends the existing Koschei vision instead of renaming another ecosystem's protocols.