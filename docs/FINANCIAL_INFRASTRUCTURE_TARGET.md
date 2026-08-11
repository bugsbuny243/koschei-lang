# Koschei Financial Infrastructure Target

Status: engineering target; not a production-readiness claim.

Koschei should eventually be capable of implementing the security-critical core
of exchange, clearing, settlement and tokenized-asset infrastructure without
requiring ambient authority, implicit floating-point money arithmetic, hidden
scheduler ordering or unsafe authority aliasing.

The target is deliberately stronger than "can compile a trading demo" or "is
pleasant to write". The hard question is:

> How difficult does Koschei make it to write a financially catastrophic system
> incorrectly?

Each phase must create executable evidence that the language and supported
runtime paths preserve the relevant invariants.

## Non-negotiable invariants

1. **No implicit floating-point money.** Prices, quantities, fees and settlement
   amounts use exact representations.
2. **Deterministic state transitions.** Equal inputs and sequencing metadata
   produce the same state transitions across supported execution paths.
3. **Authority is explicit and least-privilege.** Matching is pure. Network,
   persistence, custody and settlement sit behind separate capability boundaries.
4. **Authority ownership cannot silently alias.** Capability-bearing resources
   become affine/linear where the lifecycle requires it.
5. **Sensitive information cannot silently flow to a weaker sink.** Information
   flow becomes a type-level property, not a code-review convention.
6. **Protocol state is explicit.** Typestate makes invalid state-machine calls
   unrepresentable where practical.
7. **Transactions end in a named terminal state.** Commit/abort and recovery are
   explicit, atomic and replay-safe.
8. **Concurrency cannot change financial meaning.** Scheduler order is not a
   matching, settlement or failure-selection input unless the protocol names it.
9. **FFI cannot become an ambient escape hatch.** Foreign code is isolated behind
   explicit capability/effect contracts and audited data boundaries.
10. **Fail closed.** Overflow, unsupported rounding, corrupt recovery state,
    authority widening, information-flow violation and backend disagreement deny
    progress rather than guess.
11. **Build identity is auditable.** Release proofs bind exact source, dependency
    graph, compiler contract, MIR/backend identity and authority policy.

## High-assurance language gates

These gates are the primary language-development line. Ergonomic work remains
useful, but it does not outrank these properties.

### A0 — affine authority ownership — CURRENT

- capability-bearing values are move-only;
- ordinary method invocation borrows rather than consumes authority;
- ownership transfer through binding, call, return or aggregate is explicit;
- use-after-move fails at compile time;
- mutable affine bindings fail closed;
- capability-bearing aggregates inherit affine ownership structurally.

Reference: `docs/AFFINE_RESOURCES_V1.md`.

### A1 — mandatory effect system

The current effect inference becomes an enforceable contract:

- every function has a mechanically known effect set;
- pure functions cannot call effectful code indirectly;
- effect polymorphism is explicit rather than inferred into ambient authority;
- module/package APIs expose effect contracts as part of compatibility;
- build policy can reject effect widening.

### A2 — typestate

Security-critical handles carry protocol state in their type:

- `Transaction<Open>` cannot be settled twice;
- `Order<Active>` cannot be cancelled after terminal state;
- `Session<Authenticated>` is distinct from unauthenticated state;
- invalid transitions fail during compilation rather than runtime branch logic.

### A3 — information-flow types

- labels such as public/internal/secret/regulated become structural;
- declassification requires explicit authority and an auditable operation;
- secret values cannot flow to logs, network origins or low-integrity outputs by
  ordinary assignment/call composition;
- control-flow leaks receive explicit treatment instead of being ignored.

### A4 — atomic transaction resources

- transaction handles are linear where exactly-once termination is required;
- commit/abort are terminal typestate transitions;
- write-set/read-set and conflict semantics are explicit;
- WAL/recovery identity is bound to transaction identity;
- torn writes, duplicate commit and replay fail closed.

### A5 — capability delegation and revocation

- delegation narrows authority and records lineage;
- delegated tokens cannot widen themselves;
- revocation checks are explicit in the authority model;
- expiry/revocation semantics cannot depend on ambient wall-clock reads unless a
  trusted clock capability is explicitly present;
- ownership and revocation compose with affine/linear resource rules.

### A6 — deterministic execution contract

- deterministic ordering for externally visible state changes;
- bounded deterministic parallel primitives;
- scheduler order cannot alter result/failure selection;
- clocks, randomness and nondeterministic I/O require explicit capabilities and
  replayable inputs;
- deterministic replay/state-hash comparison becomes a release gate.

### A7 — strong FFI isolation

- no raw unrestricted host-language escape;
- imported foreign functions declare effects, memory/ownership contract and
  authority surface;
- unsafe FFI is isolated into explicitly marked audited boundary modules;
- capability tokens cannot be forged by foreign values;
- FFI ABI compatibility and implementation digest are part of build identity.

## Financial-system roadmap

### P0 — deterministic pair matching — COMPLETE

- integer price ticks and quantity lots;
- deterministic maker/taker and maker-price execution;
- invalid/non-crossing orders produce no fill;
- authority-free matching core;
- interpreter/native parity.

Reference: `examples/financial_exchange/`.

### P1 — exact financial arithmetic — COMPLETE

The first exact `Decimal` ABI uses signed-int64 atoms plus an explicit scale from
0 through 18.

P1 invariants include canonical fixed-scale parsing/serialization, checked
signed-int64 overflow, no implicit rescale, no implicit Float conversion and
backend parity.

Reference: `examples/financial_exchange/decimal_v1.ks`.

### P2 — order book and venue semantics — COMPLETE FOUNDATION

The reference venue state machine has deterministic price-time priority,
partial fills, sequence-controlled submit/cancel/replace, duplicate-id rejection,
self-trade preflight, typed deterministic events and no ambient clock/authority.

Reference: `examples/financial_exchange/order_book_v1.ks`.

### P3 — persistence and crash recovery

- append-only journal contract;
- snapshot + replay equivalence;
- corruption/torn-write detection;
- idempotent recovery;
- explicit disk capability scopes;
- recovery fuzzing and state-hash comparison.

### P4 — concurrency and throughput — FOUNDATION IN PROGRESS

Already established:

- fixed-capacity bounded queues/backpressure;
- structured task lifetime and cancellation;
- task share-safety boundary;
- race-safe native bounded queue;
- bounded deterministic native `parallel_map` with input-index result commit;
- race-detector proof for shared queue and parallel callback execution.

Still required before venue-core parallelization claims:

- deterministic sequencing boundaries for shared state;
- deadlock/fairness/resource budgets;
- ownership-safe parallel actors;
- latency/throughput benchmarks that also check financial invariants.

### P5 — clearing and settlement

- settlement state machine separate from matching;
- exact asset/amount identity;
- idempotent settlement and replay protection;
- custody/key operations behind narrow authority;
- transaction typestate + linear commit/abort resources;
- capability delegation/revocation for operators and adapters.

### P6 — production assurance

Before any NYSE/CME/Nasdaq-class claim:

- fault-injection and recovery campaigns;
- deterministic replay across supported targets;
- race/deadlock/overflow/rounding/property fuzzing;
- reproducible and attestable build chain;
- hostile FFI tests;
- effect/authority/information-flow audit reports;
- operational threat model and production maturity gate separate from language
  feature completion.

## Promotion rule

A phase is not done because a feature exists. It is done only when its invariants
are represented by deterministic tests, adversarial tests and/or benchmarks and
all supported execution paths agree.

Production exchange claims remain prohibited until a separate production
maturity gate is defined and passed.
