# Koschei First Adoption Surface v1

Status: product-entry decision; subordinate to the Koschei Library + Universe architectural contract

## Non-negotiable scope

Koschei is not reduced to a policy language.

Koschei remains a larger native computing universe composed of:

- **Koschei Lang** — the native language and semantic surface;
- **Koschei Library** — the deep verified machinery behind the visible language;
- **Koschei Universe** — the composition, lifecycle, authority, evidence, containment, recovery, visibility and epoch physics governing the whole system.

Policy/enforcement is the **first low-friction adoption surface**, not the final identity or ceiling of Koschei Lang.

The long-term architecture remains capable of native Koschei modules, services, workflows and full applications. Customers are simply not required to rewrite existing systems on day one.

## First entry path

A customer may keep an existing application in Rust, Go, Java, TypeScript, Python or another host stack and initially place Koschei at a dangerous boundary:

`existing application -> Koschei boundary -> Koschei Lang semantics -> Koschei Library -> Koschei Universe -> proof-bound enforcement -> privileged effect`

This lets Koschei enter a production architecture before the customer adopts native Koschei application code.

The entry path is deliberately progressive:

`existing system -> policy/boundary use -> privileged workflows -> native Koschei modules -> native Koschei services -> broader Koschei applications`

No stage after the first is mandatory, and the first stage must not redefine the whole language as authorization-only.

## What the first customer writes

The first end-to-end deliverable should support a small boundary program similar in scale to:

```koschei
ka treasury

vor withdrawal
    actor operator
    destination wallet
    amount request.amount
    effect signer.execute

shi withdrawal
    require intent
    require payload
    require destination
    require epoch

thal withdrawal
    stale -> reject
    duplicate -> reject
    conflict -> contain

nur withdrawal
    operator sees decision
    auditor sees proof
    nobody sees signing_secret
```

The exact grammar may evolve. The requirement is that a customer can use native Koschei semantics to govern a high-risk operation without rewriting the surrounding application.

This example is an entry program, not a definition of every program Koschei will eventually express.

## What the first customer does not need to rewrite

Initial adoption does not require rewriting:

- an exchange matching engine;
- a wallet service;
- an AI agent framework;
- a payment processor;
- a database layer;
- a deployment system;
- existing application business logic.

Koschei can receive a canonical intent envelope at a dangerous boundary, evaluate the native semantic program, expand Library obligations, apply Universe laws, and return an enforceable decision plus proof.

## Initial product boundary

The first shippable boundary product consists of:

1. **Koschei Compiler** — parses and checks the native Koschei surface used by the boundary program.
2. **Koschei Runtime / Gate** — evaluates requests at the protected execution boundary.
3. **Koschei Adapter SDK** — maps existing application requests into canonical intent envelopes without translating application source code.
4. **Koschei Library** — expands the small source program into authority, evidence, recovery, epoch, visibility and other obligations.
5. **Koschei Universe** — composes those obligations under fail-closed interaction and lifecycle laws.
6. **Koschei Proof Envelope** — machine-verifiable evidence explaining why an effect was allowed, denied or contained.

These are the first delivery surfaces of the larger Universe, not permanent limits on it.

## Competitive entry position

The first commercial wedge can be described as:

**off-chain privileged-operation enforcement with evidence-bound authority, recovery and epoch semantics.**

That entry wedge is intentionally distinct from general authorization engines, raw capability runtimes, wallet warning products and custody policy engines.

Koschei itself is broader: the same native semantics, Library and Universe are intended to support progressively more native execution rather than remain a policy sidecar forever.

Competitive claims must be proven through implementation and external comparison.

## Bybit-class claim discipline

A Koschei boundary program alone must not be claimed to prevent a compromised build/CDN/signing UI attack.

Koschei can truthfully claim authority-side guarantees only when the relevant authority was never granted or required independent evidence is absent.

A signing system that aims to address compromised presentation/build channels additionally requires independent payload acquisition/reconstruction and an enforcement point the compromised UI cannot bypass.

`authority correctness != independent signing-channel integrity`

Both are required for a full signing-security claim.

## First demo and first adoption target

The first demo should prove a real high-risk boundary rather than a broad marketplace rewrite.

A practical early wedge is AI agents / privileged automation because adoption can occur without replacing an existing application stack. Institutional treasury/custody remains a high-value target after independent security evidence exists.

The reference demo must show:

- an actor requests a dangerous effect;
- authority is explicitly bounded;
- required evidence is bound to the request;
- stale epoch is rejected;
- replay/duplicate is rejected;
- conflict produces containment;
- a proof envelope explains the decision;
- the surrounding application remains in its existing host language.

Later demos should prove native Koschei modules and services using the same Library and Universe rather than creating a separate product architecture.

## Pricing direction

Koschei Lang should not be monetized primarily as syntax.

Early commercial value is enforcement and verified operation. Candidate pricing units include protected authority domain/environment, verified privileged-effect volume, and enterprise private/HA/audit/support tiers.

As native Koschei adoption grows, packaging may expand. Exact pricing requires design-partner evidence.

## Vocabulary discipline, not permanent freeze

The current roots are:

`ka / vor / shi / thal / nur`

Engineering should not invent new roots merely to decorate domains or imitate foreign-language keywords. During the first end-to-end milestone, these five roots receive priority.

This is not a declaration that the Universe will forever contain only five words. New native roots may be introduced when a real semantic need appears and the root has a deep lexicon entry, Library obligations, Universe composition rules, lifecycle/failure behavior and executable tests.

## Immediate technical milestone

The immediate product proof is a short real boundary program traveling through the actual stack:

`source -> parser -> typed semantics -> MIR -> Library expansion -> Universe/lifecycle checks -> runtime -> proof envelope -> effect decision`

No mock planner substitutes for this path.

Acceptance requires at least:

- an allowed request succeeds;
- authority not granted is denied;
- stale epoch is denied;
- duplicate/replay is denied;
- evidence conflict contains;
- proof output is deterministic and machine-readable.

Completing this milestone proves the first doorway into Koschei Universe. It does not mark the end of language development.

## Engineering order

Near-term critical path:

1. finish canonical capability consolidation;
2. reduce/remove legacy semantic authority with parity evidence;
3. finish the MIR path required by the first native boundary program;
4. implement the five-root grammar to the depth required by that program;
5. bind Library expansion and Universe lifecycle to the real compiler/runtime path;
6. produce the proof envelope;
7. run adversarial tests outside the author's own assumptions;
8. after the doorway is real, extend native Koschei execution outward into modules, workflows, services and application domains as justified by semantic needs.

## Product sentence

**Koschei is a native security-first computing universe in which a small language surface expands through the Koschei Library and is governed by Universe-level authority, evidence, recovery, visibility and epoch laws. Its first adoption surface protects privileged effects without forcing customers to rewrite their existing systems.**
