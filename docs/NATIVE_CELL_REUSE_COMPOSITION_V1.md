# Koschei Native Cell → Reusable Composition v1

Status: **experimental language slice; stacked on Native Cell Projection v1**

## Goal

This slice proves a real application data path:

```text
sealed cell reality
  -> authenticated whole-cell bindings
  -> reusable conduit reality
  -> root conduit reality
```

It introduces no source-level member access, field lookup, function call, parameter list, module import, index syntax or runtime dispatch.

## Three authoritative source objects

V1 admits exactly three Object Space source objects:

1. root reality — consumes one sealed reusable result through one `conduit`;
2. cell reality — a full mixed-domain Native Cell Reality;
3. reusable reality — consumes contiguous `conduit` inputs and resolves one Whole/Int64 value.

The cell and reusable objects are not copied into the root source.

## Full-cell validation before input binding

The graph stores the complete cell schema table. Reusable input bindings map contiguous reusable input slots to sealed cell ordinals.

Before any reusable execution:

- every cell tag is rebound to an exact resolved source witness;
- the entire multi-root cell dependency reality is validated;
- every cell domain is checked against the sealed schema;
- selected input ordinals must exist;
- every selected input cell must be `whole` in v1;
- input absolute-value ceilings are enforced;
- reusable conduit count must exactly match the sealed binding vector.

An unselected malformed cell invalidates the composition too.

## Reusable and root admission

The reusable source is materialized only after the cell contract passes. Its witness ceiling, output absolute-value ceiling, epoch interval, authority ceiling and effect ceiling are sealed metadata.

V1 requires zero authority and zero effects.

After reusable evaluation, exactly one root `conduit` slot receives the result. The root has no other relationship aperture in v1.

## Backend boundary

Only the fully materialized root program reaches the compatibility backend. Cell witness identities, reusable witness identities, schema id, realization id, object ids and storage locators are not runtime APIs.

## Example

Cell reality:

```text
witness amount 40
witness fee 2
witness approved truth yes
resolve approved
resolve fee
resolve amount
```

Reusable reality:

```text
witness left conduit 0
witness right conduit 1
witness total sum left right
resolve total
```

Root reality:

```text
witness value conduit 0
resolve value
```

Sealed schema order is `(amount, fee, approved)` and reusable bindings are `(cell 0, cell 1)`. The full cell schema validates, then the reusable reality resolves `42`, and the root resolves `42`.

## Bounds / scope

V1 inherits:

- 4096-witness cell reality ceiling;
- 64-cell schema ceiling;
- 64 reusable inputs maximum;
- signed Int64 reusable input/output semantics;
- Object Space graph-secret budget.

## Non-claims

V1 does not yet provide:

- truth/glyph reusable inputs;
- multiple reusable realization DAGs;
- multiple cell source objects;
- nested aggregate composition;
- authority/effect-bearing reusable execution;
- JSON/HTTP/DB boundary mapping.

The purpose is narrower: prove that a sealed aggregate can feed authenticated scalar projections into reusable business logic and then into the root runtime without copying mainstream language access/call syntax.
