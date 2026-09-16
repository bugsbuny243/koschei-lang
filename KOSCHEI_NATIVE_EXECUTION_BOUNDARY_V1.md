# Koschei Native Execution Boundary v1

Status: **architectural invariant / migration gate**.

This document prevents host/bootstrap implementations from becoming language authority.
It is subordinate to `KOSCHEI_LANG_SOURCE_OF_TRUTH_2026-08-29.md` and the Galaxy Constitution.

## Canonical rule

Koschei language meaning is owned only by the Koschei compilation and sealed-execution contract:

`Koschei source -> canonical checking -> Typed HIR -> sealed Koschei MIR -> Koschei execution contract`

A host implementation may materialize or transport an already-sealed Koschei contract, but it may not define, repair, infer, reinterpret, or extend that contract.

## Authority classes

### 1. Canonical Koschei authority

The following are language-authority surfaces:

- Koschei grammar and canonical source semantics;
- structural types and Typed HIR facts;
- capability/effect/ownership/typestate contracts;
- sealed MIR identities and proof obligations;
- Koschei runtime state-transition semantics;
- Galaxy/Khar admission, evidence, finality and continuity rules.

These surfaces may not depend on a host language's type system, exception model, package model, enum resolution, authority model, or runtime semantics for their meaning.

### 2. Bootstrap/host machinery

Existing Python, Go, container, packaging and operating-system machinery is **bootstrap or adapter machinery only** while migration remains incomplete.

It is non-authoritative. In particular it MUST NOT:

- accept source or AST while bypassing canonical checking and the sealed MIR boundary;
- reconstruct compiler-owned identities from visible names;
- decide capability admission or manufacture authority;
- define a second effect, ownership, type, enum, finality or continuity semantics;
- silently accept an instruction or feature rejected by canonical Koschei admission;
- be cited as proof that a Koschei language feature exists merely because the host can emulate it.

A host backend is conforming only when its behavior is a projection of sealed Koschei facts.

## Native means Koschei-native

The word **native** in architecture and production claims means native to the Koschei execution contract. It does not mean "implemented in Go", "compiled by Python tooling", "inside a container", or "running as a host executable".

Existing modules whose historical names contain `native` are migration artifacts until their authority is proven to satisfy this boundary.

`koschei/mir_go_native.py` is therefore classified as a **host conformance adapter**, not a canonical production execution authority. Its useful fail-closed MIR parity checks may remain during migration, but adding Go-specific feature meaning is not a route to completing Koschei.

Likewise Python/Nuitka/Docker release machinery may package or test a candidate during bootstrap, but it is not part of the Koschei language definition and is not evidence of an independent Koschei runtime.

## Required migration direction

1. Preserve compiler-owned facts already normalized into sealed MIR.
2. Continue removing executable AST fallback feature by feature.
3. Define each remaining execution operation as a Koschei MIR/state-transition contract before implementing host materialization.
4. Make all host adapters consume that same sealed contract and fail closed on unsupported operations.
5. Remove host adapters from production authority claims once the Koschei-native executor can materialize the complete sealed contract without semantic delegation.
6. Keep bootstrap/build provenance separate from language/runtime authority evidence.

## Stop rules

Until the migration is complete:

- no new host-language backend may become a semantic authority;
- no backend-specific type or variant inference may flow back into compiler facts;
- no Python/Go/container behavior may resolve ambiguity in Koschei semantics;
- no release receipt may be treated as a semantic proof merely because packaging succeeded;
- no "native parity" claim may be promoted to "Koschei-native" unless the exact operation is owned by sealed Koschei MIR/state-transition semantics;
- no second privileged execution path may bypass Khar/Galaxy admission.

## PR #290 classification

The canonical Match/variant work in PR #290 remains useful where it moves identity and proof into sealed MIR (`MirVariantConstruct`, `MirVariantIs`, `MirVariantPayload`, canonical lowering, registry sealing and proof validation).

The MIR-Go work is retained only as a temporary conformance adapter/test surface. It is not the target runtime architecture. Production completion of Koschei must advance the sealed Koschei execution contract rather than expand Go as an alternate language/runtime authority.

## Evidence rule

A production claim must state separately:

- **semantic evidence** — what sealed Koschei contract was proven;
- **execution evidence** — what Koschei-native state transition was exercised;
- **bootstrap evidence** — which non-authoritative tools materialized/package-tested the candidate;
- **deployment evidence** — which physical trust roots and custody controls were actually deployed.

Evidence from one class cannot substitute for another.
