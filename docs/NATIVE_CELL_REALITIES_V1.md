# Koschei Native Cell Realities v1

Status: **experimental language slice; stacked on Native Reusable Realities v1**

## Goal

Native Cell Realities v1 adds the first bounded structured value model without exposing conventional `struct`, `record`, `tuple`, `list`, `map`, named-field, brace, bracket or colon grammar.

A cell reality is an ordered aggregate whose schema identity and cell ordering are authenticated in sealed Object Space metadata.

## Source surface

No new source keyword is introduced.

Source remains native witness/value grammar and may resolve more than one witness:

```text
witness amount 40
witness fee 2
witness total sum amount fee
witness approved truth yes
witness label glyphs 4 paid
resolve label
resolve total
resolve approved
```

The textual order of `resolve` clauses is not schema order. Sealed metadata binds the aggregate's ordered cells, for example:

```text
cell 0 -> total     (whole)
cell 1 -> approved  (truth)
cell 2 -> label     (glyphs)
```

The metadata does not persist plaintext witness names. It stores a canonical witness tag derived from project id, root object id, exact source digest and the source-local witness identity.

## Schema identity

Each cell reality binds one opaque non-zero 128-bit schema identity. The schema id is not used as a source-level type name or field name and is not emitted into the application runtime surface.

A schema contract binds:

- exact project id;
- exact root object id;
- exact source digest;
- exact native-cell frontend identity;
- opaque schema id;
- exact cell count;
- canonical ordinal sequence;
- witness tags;
- exact scalar domain per cell.

Supported v1 cell domains are `whole`, `truth`, and `glyphs`.

## Multi-root dependency reality

All sealed cell witnesses are roots of one dependency union. The frontend validates the complete reachable witness reality iteratively.

- cycles fail closed;
- unknown references fail closed;
- witnesses outside the union of all cell roots fail closed as dormant;
- source clause order and resolve-clause order do not define schema ordering;
- the 4096-witness native value ceiling remains in force.

## Backend boundary

The native cell frontend fully evaluates the closed pure witness graph before compatibility lowering.

Only canonical scalar cell values cross the frontend boundary. The compatibility AST receives a synthetic local carrier named `KCellReality` with ordinal implementation fields `c0`, `c1`, ... . This carrier is not Koschei source syntax and is not canonical project identity.

Source witness names, schema id, project id, root object id and Object Space locators must not appear in public MIR/application Go/capability/run surfaces.

## Security model

This slice intentionally avoids capability-bearing aggregate values. Only scalar native value domains are admitted, so aggregate construction cannot launder root or narrowed authority through legacy container behavior.

Object Space remains authoritative for frontend selection. There is no source sniffing, filename/extension routing or fallback from a failed cell schema into another frontend.

## Bounds

- maximum source witnesses: 4096;
- maximum cells per reality: 64;
- maximum source bytes and glyph budgets inherit Native Value Domains v1;
- graph metadata remains bounded by the Object Space sealed graph-secret limit.

## Non-claims

V1 does not yet provide:

- source-level cell projection;
- nested cell realities;
- mutable aggregates;
- open/dynamic schemas;
- named external fields;
- collections of unbounded cardinality;
- authority-bearing cells;
- automatic JSON/HTTP/DB mapping.

Those are later contracts. The purpose of v1 is narrower: establish a first-class, schema-bound, mixed-domain aggregate value and prove its canonical identity, bounds, execution parity and privacy boundary without copying mainstream aggregate syntax.
