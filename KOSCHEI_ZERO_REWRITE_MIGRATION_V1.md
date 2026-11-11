# Koschei Zero-Rewrite Migration v1

Status: architecture proposal

Koschei must be adoptable by large existing systems without requiring a company to rewrite its entire codebase before receiving value.

The migration architecture therefore treats existing software as an external system whose behavior can be observed, constrained, evidenced and gradually pulled behind Koschei semantics.

## Goal

A large exchange, marketplace, bank, cloud platform or AI system should be able to begin using Koschei around one critical execution path in hours or days, not months of wholesale rewriting.

The target adoption sequence is:

`observe -> model -> prove -> constrain -> replace selectively`

not:

`rewrite everything -> switch production`

## Koschei Migration Gate

The primary adoption product is a boundary called the **Koschei Migration Gate**.

The Gate sits between an existing application and a privileged effect such as:

- transaction signing;
- wallet or treasury movement;
- payment settlement;
- database mutation;
- deployment;
- secret use;
- privileged API calls;
- process execution;
- administrative control.

The existing application may remain written in Java, Go, Rust, Python, TypeScript, C++, Solidity tooling or another stack. The Gate does not treat those languages as Koschei semantics. It treats their outputs as untrusted external intent that must be translated into a canonical Koschei intent envelope.

## Intent Envelope

Migration does not begin by translating source code line by line.

Instead, adapters extract a minimal canonical intent:

- subject identity;
- requested effect;
- target resource;
- requested authority;
- relevant inputs/digests;
- expected state transition;
- evidence sources;
- epoch and freshness information.

That intent is then processed through Koschei:

`external request -> adapter -> canonical intent -> ka/vor/shi/thal/nur expansion -> Library proofs -> allow/deny/contain`

This avoids pretending that foreign syntax is native Koschei.

## Five adoption modes

### Mode 0 — Shadow

Koschei observes production requests and produces decisions/proofs but does not block effects.

Purpose: learn integration shape and measure false positives without operational risk.

### Mode 1 — Explain

Koschei returns a machine-readable proof envelope and operator explanation for every protected effect.

Purpose: build trust and compare Koschei decisions with existing controls.

### Mode 2 — Gate

Selected privileged effects require a valid Koschei proof before execution.

Purpose: obtain security value without rewriting the service.

### Mode 3 — Encapsulate

High-risk legacy operations move behind Koschei capabilities and Library services. Existing business logic remains foreign, but authority and evidence boundaries become Koschei-owned.

### Mode 4 — Native

Only components that benefit enough are rewritten in native Koschei source. Migration is selective, evidence-driven and reversible at subsystem boundaries.

## Adapter rule

Adapters are allowed to understand foreign APIs, protocols and data formats. They are not allowed to define Koschei meaning.

An adapter may say:

`this legacy request appears to request transfer X from account A to account B`

but only canonical Koschei contracts decide whether the identity is admitted, authority is sufficient, evidence is final, recovery is safe and visibility is appropriate.

## No source-to-source illusion

A generic JavaScript-to-Koschei or Go-to-Koschei source converter cannot be the primary migration strategy. Automatic source translation cannot infer business authority, evidence requirements, recovery semantics or visibility boundaries reliably enough to claim Koschei guarantees.

Source translation may later assist developers, but translated code remains untrusted until it passes canonical Koschei semantic analysis and explicit migration mappings.

## Enterprise adoption promise

The intended customer promise is:

**Keep your existing application. Put Koschei in front of the effects that can hurt you. Move deeper only when the proof shows value.**

## Binance-scale example

An exchange does not rewrite matching engines, account services, custody, risk, settlement and frontend systems on day one.

First protected path might be treasury signing:

1. Existing services construct a withdrawal or treasury payload.
2. A Koschei adapter extracts canonical identity, destination, amount, chain, payload digest and requested signer authority.
3. `ka` binds request and actor identity.
4. `vor` proves the exact bounded signing authority.
5. `shi` binds independent transaction, policy and state evidence.
6. `thal` defines duplicate/replay/conflict/partial-failure behavior.
7. `nur` restricts unnecessary internal topology exposure.
8. Koschei Library emits a sealed proof envelope.
9. HSM/MPC/signer accepts only a valid envelope.

The exchange receives Koschei protection while the upstream services remain in their existing languages.

## Migration safety invariants

1. Foreign code is never silently considered native Koschei.
2. Adapters cannot mint authority.
3. Unknown or ambiguous intent fails closed in Gate mode.
4. Shadow mode can never grant production authority.
5. Proof identity binds the exact protected effect, not merely the surrounding request.
6. Replay across epoch, resource, actor or payload is rejected.
7. Legacy fallback cannot bypass a configured Koschei Gate.
8. Each migration boundary can be independently rolled out and measured.
9. Native rewrite is optional and selective.
10. Koschei guarantees begin at the boundary actually controlled by Koschei; marketing must not imply protection of unobserved/uncontrolled legacy paths.

## Strategic consequence

Koschei becomes adoptable as an execution-security layer before it becomes the customer's primary programming language.

This is not a compromise of the language vision. It is the migration bridge into that vision:

`existing world -> Koschei Gate -> Koschei Library/Universe -> progressively native Koschei`
