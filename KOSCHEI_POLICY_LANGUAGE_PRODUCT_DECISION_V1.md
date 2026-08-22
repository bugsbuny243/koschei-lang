# Koschei Policy Language Product Decision v1

Status: product and architecture decision

## Decision

Koschei is not positioned as the primary language in which customers rewrite their applications. Koschei is positioned first as the language in which customers express and enforce privileged authority.

The customer keeps the application implementation in Rust, Go, Java, TypeScript, Python or another host stack. Koschei owns the privileged-operation policy boundary.

Primary model:

`existing application -> Koschei policy -> Koschei Library -> Koschei Universe -> proof-bound enforcement -> privileged effect`

The language is therefore delivered first as an enforceable policy language with a verified runtime, not as a wholesale application rewrite requirement.

## What the customer writes

The first deliverable must support a small policy similar in scale to the following:

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

The exact grammar may evolve, but the product requirement does not: a customer must be able to express a privileged-operation policy in a short native Koschei document without rewriting the application that requests the operation.

## What the customer does not write

The customer does not rewrite:

- the exchange matching engine;
- the wallet service;
- the AI agent framework;
- the payment processor;
- the database layer;
- the deployment system;
- the existing application business logic.

Koschei receives a canonical intent envelope at the dangerous boundary, evaluates policy and evidence, and returns an enforceable decision plus proof.

## Product boundary

The initial product consists of:

1. **Koschei Policy Compiler** — parses and checks the small `.ks` policy surface.
2. **Koschei Enforcement Runtime / Gate** — evaluates requests at the privileged boundary.
3. **Koschei Adapter SDK** — maps an existing application's request into a canonical intent envelope without translating application source code.
4. **Koschei Library** — expands the small policy into authority, evidence, recovery, epoch and visibility obligations.
5. **Koschei Universe** — composes those obligations under fail-closed interaction and lifecycle rules.
6. **Koschei Proof Envelope** — machine-verifiable explanation of why a privileged effect was allowed, denied or contained.

## Competitive position

Koschei's intended slot is:

**off-chain privileged-operation policy with evidence-bound authority, recovery and epoch semantics.**

This is intentionally distinct from:

- general application languages;
- on-chain asset languages such as Move;
- general authorization policy engines such as Cedar/Rego;
- raw capability runtimes such as WASI;
- wallet simulation or transaction-warning products;
- custody policy engines that do not make evidence/recovery/epoch first-class language semantics.

This positioning must be proven through implementation and external comparison; it is not assumed merely by naming the category.

## Bybit-class claim discipline

Koschei must not claim that writing treasury policy alone prevents a compromised build/CDN/signing UI attack.

Koschei can truthfully claim authority-side guarantees only when the relevant authority was never granted or the independent evidence required for the effect is missing.

A signing product that aims to address compromised presentation/build channels additionally requires independent payload acquisition/reconstruction and an enforcement point that the compromised UI cannot bypass.

Therefore:

`policy correctness != independent signing-channel integrity`

Both are required for a full signing-security claim.

## First ICP and first demo

The first demo must belong to the first sellable wedge, not to a broad marketplace example.

Primary wedge for speed of adoption:

**AI agents and privileged automation with real tool authority.**

Institutional treasury/custody remains a high-value second target after independent security evidence exists.

The first reference demo should prove the same core semantics in a privileged-operation flow:

- an actor requests a dangerous effect;
- authority is explicitly narrowed;
- required evidence is bound to the request;
- stale epoch is rejected;
- replay/duplicate is rejected;
- conflict produces containment;
- a proof envelope explains the decision;
- the existing application remains in its host language.

A treasury/signer demo should follow using the same policy engine once the boundary and proof model are independently testable.

## Pricing direction

The language specification and local policy tooling should not be the primary monetization surface.

Commercial value is enforcement.

Candidate pricing units:

- protected vault / protected authority domain per year;
- protected environment per year;
- verified privileged-effect volume;
- enterprise HA/private deployment/audit/support tier.

Exact pricing must follow design-partner interviews and measured customer value, not invented list prices.

## Vocabulary freeze

The current semantic roots are sufficient for the first product milestone:

`ka / vor / shi / thal / nur`

Do not expand into marketplace, messaging, storage, finance or other root vocabularies until the first policy compiles and enforces end to end.

New vocabulary is blocked unless required by the first policy milestone and justified by a semantic need that cannot be expressed through the existing five roots.

## Single technical milestone

The product is not considered born until a short real policy travels through the actual language stack:

`source -> parser -> typed semantics -> MIR -> Library expansion -> Universe/lifecycle checks -> enforcement runtime -> proof envelope -> ALLOW/DENY/CONTAIN`

No mock planner may substitute for this end-to-end path.

The acceptance test is a policy of roughly 10-20 lines that can be executed against a real privileged-operation request and demonstrates:

- allowed request succeeds;
- authority not granted is denied;
- stale epoch is denied;
- duplicate/replay is denied;
- evidence conflict contains;
- proof output is deterministic and machine-readable.

## Engineering order

Until the milestone above passes, engineering priority is locked to:

1. finish canonical capability consolidation;
2. reduce/remove legacy semantic authority with parity evidence;
3. finish the MIR path needed for the first policy;
4. implement the five-sigil policy grammar only to the depth required by the first policy;
5. bind Library expansion and Universe lifecycle to the real compiler/runtime path;
6. produce the proof envelope;
7. run adversarial tests outside the author's own assumptions.

Do not spend the critical path on new semantic roots, marketplace demos, decorative Universe expansion or additional platform modules that do not move the first policy toward end-to-end execution.

## Product sentence

**Koschei is the language in which high-risk software writes its authority, and the runtime that refuses privileged effects unless that authority is evidence-bound, current and provable.**
