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
available SSA values; the key is a canonical String; sealed instruction type
agrees with builder type.

Transition: append the exact evaluated pair in MIR order.

**Canonical duplicate-key policy: reject.** A key already present in the builder
MUST fail closed before overwrite. Literal duplicates are rejected during
checking with KS1501; dynamically-equal keys are rejected by execution. No host
dictionary last-write-wins behavior is part of Koschei semantics.

### MirMapFinish(target, source, type)
Preconditions: source is a live unfinished map-builder; sealed type agrees; map
invariants are canonically decidable.

Transition: consume/seal the builder exactly once and bind target to the
immutable canonical Map value. Insert/finish after consumption is invalid.
Insertion order is part of the observable keys/rendering contract.

### MirMapGet(target, object, key, type)
Preconditions: object is a sealed canonical Map; key is String.

Transition: read the exact key without mutating the Map. A present key yields
its stored value. A missing key yields the canonical fallible error path used by
Koschei `or` handling. No host exception or host mapping default is semantic
authority.

### MirMapSet(target, object, key, value, type)
Preconditions: object is a sealed canonical Map; key is String; value has passed
the canonical checked capability/type contract.

Transition: produce a new Map value. If the key exists, replace its value while
preserving its original position. If the key is new, append it at the end.
The source Map is unchanged.

### MirMapKeys(target, object, type)
Preconditions: object is a sealed canonical Map.

Transition: produce a canonical List of keys in Map insertion order.

### MirMapContains(target, object, key, type)
Preconditions: object is a sealed canonical Map; key is String.

Transition: produce Bool indicating exact key membership without mutation.

## Struct transitions

### MirStructNew(target, type_name, required_fields, type)
Preconditions: exact MIR v4 instruction; type_name, required_fields and type are
compiler-owned sealed facts; required_fields contains no duplicate; target is
fresh.

Transition: create a private unfinished struct-builder carrying exact sealed
identity, declaration-owned required-field order and an empty assignment set.
Runtime lookup MUST NOT change identity or required-field order.

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
exact identity and field/value bindings in declaration-owned order. No runtime
may invent missing defaults unless those defaults were explicitly lowered into
sealed MIR.

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
   struct fields, duplicate Map insertion, non-String Map keys and invalid
   aggregate receiver shapes;
5. bootstrap evidence is reported separately and cannot substitute for 1-4.

## Current migration gate

The canonical contracts now cover:
- Map construction/finalization and duplicate rejection;
- Map get/set/keys/contains method semantics;
- Struct declaration-owned required-field identity/order;
- Struct construction/finalization.

Remaining closure is **validation evidence**, not semantic ambiguity: the exact
candidate head must pass the canonical validation profile and retain its receipt.
Host runtimes remain non-authoritative materializers of the sealed contract.
