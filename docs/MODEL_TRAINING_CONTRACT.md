# Koschei Model Training Contract v1

Status: canonical training-source contract for models learning Koschei Language  
Scope: compiler/spec/tests/examples exported into an offline model curriculum  
Production status: research only; this document does not integrate any model into the compiler/runtime

## Goal

A model that participates in the Koschei ecosystem must learn Koschei Language from the language implementation and its executable rules, not from prose imitation or translated Rust/Go/Python code.

The target is not "good autocomplete". The target is a model that can:

- write idiomatic Koschei;
- explain exact capability boundaries;
- diagnose invalid authority use;
- repair code without widening authority;
- reason about type, error, module and capability semantics;
- identify supply-chain and privilege-escalation attempts;
- preserve security invariants while refactoring;
- abstain when a language feature is not implemented or the source version is unknown.

## Source of truth order

When training material conflicts, authority is resolved in this order:

1. compiler behavior for the pinned source revision;
2. executable test suite and committed golden diagnostics;
3. versioned language/runtime contracts;
4. canonical examples that pass the compiler for that same revision;
5. documentation for that same revision;
6. model-generated explanations.

A model output is never a language specification.

## Compiler-oracle rule

Every generated training example that claims a program is valid must be checked by the pinned Koschei compiler.

Every generated negative example must assert the exact failure class expected from that same compiler revision.

Training pipeline:

```text
pinned Koschei source revision
        ↓
canonical spec + tests + examples
        ↓
training-case generator
        ↓
ks check / ks caps / targeted test oracle
        ↓
accepted or rejected example
        ↓
immutable curriculum release
```

No compiler result means no authoritative training label.

## Required curriculum families

### L0 — Syntax and core semantics

- functions and typed parameters;
- immutable and mutable bindings;
- structs and enums;
- `Option<T>` and `Result<T,E>`;
- exhaustive `match`;
- collections;
- module/import behavior;
- error propagation;
- interpolation and daily standard-library behavior.

### L1 — Capability fundamentals

The model must internalize:

> Authority cannot appear from nowhere.

Required cases include:

- disk access without a disk capability;
- network access without a network capability;
- environment access without an environment capability;
- process access without a process capability;
- root capability used directly when delegation is required;
- narrowing a capability;
- attempted re-widening after narrowing;
- passing a narrow capability through several functions;
- dependency code attempting to inherit parent-process authority;
- pure code remaining capability-empty.

### L2 — Adversarial authority cases

The corpus must contain verified negative examples for attempts such as:

- path traversal;
- symlink escape;
- read-only token used for writes;
- redirect leaving an allowed network origin;
- environment-secret exfiltration;
- hidden network access through a dependency;
- process-spawn escape;
- native/FFI boundary misuse when such boundaries are available;
- confused-deputy style delegation;
- capability laundering through helper functions;
- malicious package update adding new reach.

A repair is accepted only if the attack is stopped without silently granting broader authority.

### L3 — Backend and systems programs

The model must learn that high security is not feature prohibition. Training programs should exercise powerful legitimate use:

- network services;
- storage-backed services;
- concurrent workloads as supported by the language revision;
- parsers and data pipelines;
- Web3 data processing fixtures;
- process/system boundaries where implemented;
- native builds and interpreter/native parity.

The expected principle is:

> Maximum declared power, minimum ambient authority.

### L4 — Security-preserving repair

For each vulnerable/invalid program, the model receives tasks such as:

- explain the violated invariant;
- produce the minimum-authority repair;
- show the resulting capability manifest;
- reject a proposed repair that merely adds a broad root capability;
- preserve program behavior while reducing authority.

## Required negative-transfer rule

Training must not teach the model to mechanically translate other languages into Koschei.

Bad curriculum goal:

```text
Rust source -> equivalent-looking Koschei syntax
Go source   -> equivalent-looking Koschei syntax
```

Correct goal:

```text
problem + constraints + security authority
        ↓
idiomatic Koschei design
```

Rust, Go, Python, C/C++ and WASM may be used for interoperability fixtures and comparative benchmarks, but they are not syntax or execution-model templates for Koschei.

## Capability-security hard gates

A language-learning candidate fails promotion if any tested case allows it to recommend or generate a repair that:

1. turns a narrow capability into a broader one without explicit authority;
2. gives a dependency ambient disk/network/env/process access;
3. bypasses a compiler diagnostic instead of solving the cause;
4. hides a new capability from the capability manifest;
5. changes a security failure into silent success;
6. treats model confidence as permission;
7. invents an unavailable language feature as implemented;
8. claims a program compiled when the pinned compiler rejected it.

## Future Sentinel relationship

Sentinel may learn this curriculum offline. It receives no authority merely because it knows the language.

When a future integration is separately approved:

- compiler/type/capability rules remain deterministic authority;
- Sentinel may observe, classify, explain, recommend restriction or request quarantine;
- Sentinel must not grant a new capability;
- Sentinel must not widen a capability;
- Sentinel must not bypass compiler/runtime policy;
- Sentinel must not declare its own output equivalent to a compiler result.

The intended defense is layered:

```text
Sentinel recognizes suspicious behavior
              +
Koschei Language enforces hard authority boundaries
```

Either layer may catch a problem the other did not recognize; neither may silently weaken the other.

## Future KOSCH relationship

A verified KOSCH proof may eventually be exposed to an application as a bounded application-level authorization input after the language and ecosystem integration gates are passed.

It must never be a root capability and must never imply:

- compiler bypass;
- capability widening;
- unsafe FFI permission;
- model promotion;
- verdict authority;
- evidence mutation.

Token proof can participate in an authorization decision; it cannot manufacture technical authority.

## Curriculum release requirements

Every real curriculum release must record:

- exact Koschei repository commit SHA;
- compiler/toolchain version;
- spec/schema version;
- source file digests;
- test-suite result summary;
- accepted/rejected example counts;
- diagnostic-code distribution;
- capability-family distribution;
- negative/adversarial case distribution;
- train/validation/test split rule;
- release digest.

A mutable branch name such as `main` is not sufficient provenance for a training release.

## Acceptance principle

The model should know Koschei deeply, but trust remains executable:

> The model proposes. The compiler proves what the implementation actually accepts.
