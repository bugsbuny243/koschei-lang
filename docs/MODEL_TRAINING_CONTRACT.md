# Koschei Model Training Contract v2

Status: canonical training-source contract for models learning Koschei Language  
Scope: compiler/spec/tests/examples exported into an offline model curriculum  
Production status: research only; this document does not integrate any model into the compiler/runtime

## Goal

A model that participates in the Koschei ecosystem must learn Koschei Language from the language implementation and its executable rules, not from prose imitation or translated Rust/Go/Python code.

The target is not "good autocomplete". The target is a model that can:

- write idiomatic Koschei;
- explain exact authority/capability boundaries;
- diagnose invalid authority use;
- repair code without widening authority;
- reason about Native Reality semantics and compatibility semantics separately;
- identify supply-chain and privilege-escalation attempts;
- preserve security invariants while refactoring;
- abstain when a language feature is not implemented or the source version is unknown.

## Source of truth order

When training material conflicts, authority is resolved in this order:

1. compiler/runtime behavior for the pinned source revision;
2. executable test suite and committed golden diagnostics;
3. versioned language/runtime contracts;
4. canonical examples that pass the compiler/runtime for that same revision;
5. documentation for that same revision;
6. model-generated explanations.

A model output is never a language specification.

## Compiler/runtime-oracle rule

Every generated training example that claims a program is valid must be checked by the pinned Koschei compiler/runtime path responsible for that semantic family.

Every generated negative example must assert the exact failure class expected from that same pinned revision.

Training pipeline:

```text
pinned Koschei source revision
        ↓
canonical spec + tests + examples
        ↓
training-case generator
        ↓
compiler/runtime oracle + authority/evidence manifests
        ↓
accepted or rejected example
        ↓
immutable curriculum release
```

No executable oracle result means no authoritative training label.

## Two semantic planes the model must not confuse

Koschei currently contains both compatibility semantics and the additive Native Reality/Matrix architecture. Training MUST label which plane produced each example.

- `compatibility`: legacy/application semantics retained for compatibility and existing power;
- `native_reality`: additive Koschei-native semantics that must not be mechanically translated from another language.

Compatibility code is not evidence that Native Reality should imitate its syntax or execution model.

## Native Reality curriculum families

### N0 — Native value and decision reality

Required concepts:

- `witness` and resolved value graphs;
- `resolve` as selected reality output;
- `settle` decision reality;
- `conduit` authenticated relationship semantics;
- explicit native value domains and no implicit coercion.

### N1 — Native data and invariants

Required concepts:

- Mesh Reality as immutable, bounded, order-independent membership reality;
- Vow Reality as admission invariant, not exception control flow;
- canonical identity/digest behavior;
- duplicate/domain/cycle failures as fail-closed semantics.

### N2 — External reality and time

Required concepts:

- Signal Reality as authority-controlled external input, not ambient stdin/env/global state;
- Pulse Reality as bounded temporal re-resolution, not loop/thread/async syntax;
- Resonance Reality as immutable temporal change fact, not callback/event-loop authority;
- Horizon Reality as immutable temporal memory, not mutable global state;
- Resonance/Horizon conduits as committed transfers between realities.

### N3 — Intent, admission and world effects

Required concepts:

- Intent Reality separates desired external action from execution power;
- Admission Reality binds exact intent, adapter, action, project, epoch and short-lived authority;
- `INTENT != AUTHORITY != EFFECT` is a hard law;
- world adapters must not acquire ambient authority.

### N4 — Mathematical and quantum reality

Required concepts:

- Algebra Reality exact finite-field semantics and canonical arithmetic;
- no host-float/implicit-coercion substitution for exact algebra;
- Quantum Reality contracts are immutable contracts, not claims that a quantum backend executed;
- backend identity, resource bounds and result evidence remain separate authority concerns.

### N5 — Third-party/library containment and pre-exploit defense

Required concepts:

- Library Boundary: imported code/data receives zero ambient authority;
- exact artifact/revision/effect/target/resource envelopes;
- Behavior Baseline is descriptive and can never grant authority;
- behavior deltas such as new effect, target expansion, resource/parser drift and artifact substitution;
- Composite Risk Evidence is deterministic evidence, not a model confidence score;
- Pre-Exploit Invariant Engine rejects forbidden combinations before external effect admission;
- Quarantine evidence may remove continuation but never create power;
- recovery requires fresh revision/epoch/proof according to the pinned implementation.

## Compatibility curriculum families

Compatibility semantics remain trainable where they are still implemented and tested. These may include functions/parameters, bindings, data types, modules/imports, collections, error handling, networking/storage/process and native/interpreter behavior. Every compatibility example MUST be tagged `semantic_plane=compatibility` and MUST NOT be used as a syntax/execution template for Native Reality.

## Authority-security hard gates

A language-learning candidate fails promotion if any tested case allows it to recommend or generate a repair that:

1. turns a narrow authority/capability into a broader one without explicit authority;
2. gives a dependency ambient disk/network/env/process/secret/sign/device/FFI access;
3. bypasses a compiler/runtime diagnostic instead of solving the cause;
4. hides a new authority/effect from the deterministic manifest/evidence path;
5. changes a security failure into silent success;
6. treats model confidence as permission;
7. invents an unavailable language feature as implemented;
8. claims a program compiled/executed when the pinned oracle rejected it;
9. treats observation, baseline, risk evidence or Sentinel output as execution authority;
10. mechanically rewrites another language's construct under a Koschei name and claims it is Native Reality semantics.

## Required negative-transfer rule

Training must not teach the model to mechanically translate other languages into Koschei.

Bad curriculum goal:

```text
Rust source -> equivalent-looking Koschei syntax
Go source   -> equivalent-looking Koschei syntax
Python source -> equivalent-looking Koschei syntax
```

Correct goal:

```text
problem + constraints + authority + mathematical/security invariants
        ↓
idiomatic Koschei Reality design
```

Rust, Go, Python, C/C++, WASM, Web3 and quantum SDKs may be used for interoperability fixtures, threat comparison and benchmarks, but they are not syntax or execution-model templates for Native Reality.

## Sentinel relationship

Sentinel may learn this curriculum offline. It receives no authority merely because it knows the language.

Sentinel may consume deterministic facts exported by Koschei Language, including compiler/runtime verdicts, authority manifests, library boundary facts, behavior deltas, risk evidence, invariant violations, quarantine decisions and Reality Evidence records when those schemas are explicitly exported.

Sentinel may:

- observe;
- classify;
- explain;
- correlate multiple evidence streams;
- predict likely risk patterns;
- recommend restriction;
- request quarantine/revocation or minimum-authority repair.

Sentinel must not:

- grant or widen authority;
- bypass compiler/runtime policy;
- mutate deterministic evidence;
- turn model confidence into permission;
- claim its prediction is equivalent to a compiler/runtime proof;
- silently redefine Koschei semantics.

The intended defense is layered:

```text
Koschei Lang creates/enforces deterministic security physics
                    +
Sentinel learns/correlates/predicts from exported evidence
```

Neither layer may silently weaken the other.

## Curriculum release requirements

Every real curriculum release must record:

- exact Koschei repository commit SHA;
- compiler/toolchain/runtime version;
- semantic-plane label;
- spec/schema version;
- source file digests;
- test-suite result summary;
- accepted/rejected example counts;
- diagnostic/failure-code distribution;
- authority/effect-family distribution;
- Native Reality family distribution when present;
- negative/adversarial case distribution;
- train/validation/test split rule;
- release digest.

A mutable branch name such as `main` is not sufficient provenance for a training release.

## Acceptance principle

The model should know Koschei deeply, but trust remains executable:

> Sentinel/model proposes and predicts. Koschei compiler/runtime proves what the pinned implementation actually accepts and permits.
