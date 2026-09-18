# Koschei Sealed Aggregate State Transitions v1

Status: **canonical execution contract / implementation gate**.

Subordinate to `KOSCHEI_LANG_SOURCE_OF_TRUTH_2026-08-29.md`,
`KOSCHEI_GALAXY_CONSTITUTION_V1.md`, and
`KOSCHEI_NATIVE_EXECUTION_BOUNDARY_V1.md`.

This defines execution meaning for the registered sealed MIR v4 aggregate
instructions. It grants no authority to Python, Go, containers, or other hosts.

## Invariant

Only compiler-admitted sealed MIR may request these transitions. An executor
materializes the transition; it MUST NOT infer missing type names, field names,
field order, key/value types, mutability, defaults, or authority. Ambiguous or
malformed state is rejected.

## Map transitions

### MirMapNew(target, type)
Preconditions: exact MIR v4 instruction; compiler-selected sealed result type;
fresh SSA target.

Transition: create a private unfinished map-builder bound to target. The builder
is not a language Map value and is not externally observable.

### MirMapInsert(object, (key, value), type)
Preconditions: object is a live unfinished MirMapNew builder; key/value are
available SSA values; sealed instruction type agrees with builder type.

Transition: append the exact evaluated pair in MIR order.

Duplicate keys are a canonical-language decision, not a host-container decision.
Until canonical Koschei fixes that policy, an executor MUST fail closed on a
duplicate rather than inherit host dictionary overwrite behavior.

### MirMapFinish(target, source, type)
Preconditions: source is a live unfinished map-builder; sealed type agrees; map
invariants are canonically decidable.

Transition: consume/seal the builder exactly once and bind target to the
immutable canonical Map value. Insert/finish after consumption is invalid.

## Struct transitions

### MirStructNew(target, type_name, type)
Preconditions: exact MIR v4 instruction; type_name and type are compiler-owned
sealed facts; target is fresh.

Transition: create a private unfinished struct-builder carrying exact sealed
identity and an empty assignment set. Runtime lookup MUST NOT change identity.

### MirStructSet(object, field, source, type)
Preconditions: live unfinished builder; field is an exact compiler-admitted field
identity; source is available; type agrees; field has not already been assigned.

Transition: record exactly one assignment.

Unknown field, duplicate assignment, type disagreement, consumed builder, or
missing compiler-owned field evidence is fail-closed.

### MirStructFinish(target, source, type)
Preconditions: live unfinished builder; type agrees; assigned fields exactly
equal the compiler-admitted required field set.

Transition: consume/seal once and bind target to an immutable Struct carrying
exact identity and field/value bindings. No runtime may invent missing defaults
unless those defaults were explicitly lowered into sealed MIR.

## Error propagation

Errors produced while evaluating Map/Struct child expressions are represented by
canonical surrounding control flow. Aggregate instructions do not create a
second exception/recovery model. A host exception is not a Koschei result.

## Evidence obligations

A feature may be called Koschei-native execution only when:
1. lowering evidence binds source/Typed-HIR facts to exact registered MIR;
2. seal evidence validates identity, SSA/control flow and compiler-owned facts;
3. execution evidence exercises transitions without source/AST consultation;
4. adversarial evidence rejects forged identity, builder reuse, invalid/missing
   struct fields and unresolved duplicate-map-key semantics;
5. bootstrap evidence is reported separately and cannot substitute for 1-4.

## Current migration gate

`MirMapNew/Insert/Finish` and `MirStructNew/Set/Finish` are canonical
representation facts once sealed. Existing host runtimes remain non-authoritative
adapters.

Two gaps MUST be closed before execution support is claimed:
- canonical Map duplicate-key semantics;
- sealed compiler-owned Struct required-field identity/set available at the
  execution boundary.

Runtime reconstruction from arbitrary host objects is forbidden.
