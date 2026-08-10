# Koschei Financial Infrastructure Target

Status: engineering target; not a production-readiness claim.

Koschei should eventually be capable of implementing the security-critical core
of exchange, clearing, settlement and tokenized-asset infrastructure without
requiring ambient authority or floating-point money arithmetic.

The target is deliberately stronger than "can compile a trading demo". Each
phase must create executable evidence that the language and both runtime paths
preserve the relevant financial invariants.

## Non-negotiable invariants

1. **No implicit floating-point money.** Prices, quantities, fees and settlement
   amounts must use exact representations. P0 uses integer ticks/lots; P1 adds a
   first-class exact fixed-point contract.
2. **Deterministic state transitions.** Equal inputs and sequencing metadata must
   produce the same fills and state transitions across interpreter/native paths.
3. **Price-time priority is explicit.** Matching policy is data + code, never
   hidden in host-language container iteration behavior.
4. **Authority is least-privilege.** Matching is pure. Network, persistence,
   custody and chain settlement live behind separate capability boundaries.
5. **Fail closed on overflow, unsupported rounding, corrupt recovery state,
   authority widening and backend disagreement.**
6. **Build identity is auditable.** Release/reproducibility proofs must bind the
   exact source, MIR, dependency lock and authority contracts used by the binary.

## Roadmap

### P0 — deterministic pair matching — COMPLETE

- `Order`, `Trade`, `Side` contracts in Koschei.
- Integer price ticks and quantity lots only.
- deterministic maker/taker and maker-price execution.
- invalid/non-crossing orders produce no fill.
- zero side-effect capability in the matching core.
- interpreter/native byte parity.

Reference: `examples/financial_exchange/`.

### P1 — exact financial arithmetic — CURRENT

The first exact `Decimal` ABI uses signed-int64 atoms plus an explicit scale from
0 through 18. Its initial public surface is:

- `decimal(String, Int) -> Decimal or Error`;
- `decimal_add(Decimal, Decimal) -> Decimal or Error`;
- `decimal_sub(Decimal, Decimal) -> Decimal or Error`;
- `decimal_cmp(Decimal, Decimal) -> Int or Error`;
- `decimal_text(Decimal) -> String`.

Current P1 invariants:

- no binary floating-point representation in the Decimal runtime;
- canonical input and fixed-scale serialization;
- checked signed-int64 overflow;
- different scales fail closed instead of rescaling implicitly;
- no implicit `Float <-> Decimal` conversion;
- interpreter, direct-MIR and generated-Go adapters share the same contract.

Multiplication, division and rescaling remain intentionally unavailable until
explicit rounding modes and their adversarial parity vectors are specified.

Reference: `examples/financial_exchange/decimal_v1.ks`.

### P2 — order book and venue semantics

- deterministic price-time priority over many orders;
- cancel/replace and partial fills;
- monotonic sequence numbers;
- duplicate order-id rejection;
- tick-size / lot-size validation;
- self-trade and risk policy hooks;
- deterministic event log.

### P3 — persistence and crash recovery

- append-only journal contract;
- snapshot + replay equivalence;
- corruption/torn-write detection;
- idempotent recovery;
- explicit disk capability scopes;
- recovery fuzzing and state-hash comparison.

### P4 — concurrency and throughput

Concurrency is not allowed to change matching semantics.

- bounded queues/backpressure;
- deterministic sequencing boundary;
- actor/task isolation;
- cancellation semantics;
- race/deadlock stress tests;
- latency/throughput benchmarks with invariant checks.

### P5 — clearing and settlement adapters

- settlement state machine separate from matching;
- custody/key operations behind narrow authority;
- network origins capability-scoped;
- chain/provider adapters cannot widen authority;
- idempotent settlement and replay protection;
- exact asset/amount identity in every transition.

### P6 — security intelligence gate

Only after Sentinel and the language independently pass their maturity gates:

- pre-trade / pre-settlement risk evidence can be supplied by Sentinel;
- Sentinel output remains advisory/evidence-bearing;
- deterministic Koschei policy is final for execution authority;
- AI output cannot forge capability tokens, mutate signed state, or override
  compiler/runtime invariants.

## Promotion rule

A phase is not "done" because a feature exists. It is done only when its
invariants are represented by deterministic tests/benchmarks and both supported
execution paths agree. Production exchange claims remain prohibited until a
separate production maturity gate is defined and passed.
