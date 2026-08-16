# Koschei Native Mixed-Domain Reuse v1

Status: **experimental language slice; stacked on Native Cell → Reusable Composition v1 (#204)**

## Goal

Carry the existing native scalar realities — `whole`, `truth`, and `glyphs` — from one fully authenticated Native Cell Reality into reusable business logic without adding `.field`, bracket/index access, function declarations, parameter lists, calls, imports, structs, records, tuples, maps, or runtime dispatch.

The source-level aperture remains `conduit`; the authority to bind a conduit to a particular cell ordinal and scalar domain exists only in sealed Object Space metadata.

## Mixed input contract

Each reusable input binding seals:

- contiguous reusable input slot;
- exact cell ordinal in the complete cell schema;
- exact scalar domain repeated from the sealed cell record.

The complete cell schema is validated before any selected input is materialized. A malformed or domain-tampered unselected cell still invalidates the composition.

Supported reusable input domains are:

- `whole` — signed Int64, with sealed absolute-value ceiling;
- `truth` — canonical `yes` / `no` reality;
- `glyphs` — canonical NFC UTF-8, with sealed byte ceiling.

There is no implicit coercion between them.

## Typed reusable materialization

A reusable source can combine the authenticated conduit values using the existing native value-domain operations. Example:

```text
witness amount conduit 0
witness approved conduit 1
witness label conduit 2
witness amountok same amount 40
witness expected glyphs 2 ok
witness labelok same label expected
witness approvalok same approved amountok
witness result same approvalok labelok
resolve result
```

`conduit` witnesses are replaced internally with authenticated `NativeValue` atoms before value-domain evaluation. Placeholder source is parsed only to establish canonical syntax/dependency structure; placeholder values are never evaluated as program truth.

## Sealed result domain

The graph also seals the expected reusable result domain. Load fails closed if the reusable reality resolves a different domain, even if the resulting payload could otherwise be represented by the backend.

This prevents a graph or source substitution from silently changing a reusable contract from, for example, `truth` to `glyphs`.

The root then consumes exactly that typed result through one sealed conduit. V1 uses root result slot `0`.

## Resource policy

V1 seals independent resource ceilings for:

- reusable witness count;
- absolute Whole input magnitude;
- absolute Whole output magnitude;
- Glyphs input bytes;
- Glyphs output bytes;
- issued / expiry Object Space epoch;
- authority ceiling;
- effect ceiling.

Authority and effect ceilings remain zero in v1.

## Backend boundary

Only the completely materialized root program reaches compatibility lowering. Project id, object ids, schema id, realization id, cell witness tags, storage locators, and binding ordinals are not source/runtime APIs.

## Non-claims

This slice does not yet provide multiple reusable realization DAGs, multiple cell source objects, nested aggregate composition, effect-bearing reusable execution, external JSON/HTTP/DB admission, or dynamic domain selection.

The next pressure after this slice is a typed external boundary that can map untrusted wire data into sealed native scalar/cell realities without turning JSON field names, HTTP routes, or database columns into ambient source authority.
