# Koschei Native Cell Projection v1

Status: **experimental language slice; stacked on Native Cell Realities v1**

## Goal

Projection v1 makes one scalar cell consumable from a sealed Native Cell Reality without adding conventional member access, dot syntax, bracket indexing, `get`, field names, tuple projection or unchecked runtime indexing.

## No new source syntax

The source remains the same multi-resolve native cell witness reality. Projection is selected only by authenticated Object Space metadata.

A projection contract binds:

- exact project id;
- exact root object id;
- exact source digest;
- distinct projection frontend identity;
- opaque non-zero cell schema identity;
- the complete ordered cell table;
- selected cell ordinal;
- selected scalar domain.

The complete cell table is retained deliberately. Projection is not permission to validate only one value. Every sealed cell witness and its dependency reality is checked before the selected value can cross the frontend boundary.

## Full-schema-first rule

For every projection:

1. authenticate project/root/source/frontend/schema context;
2. decode the entire canonical ordinal table;
3. bind every cell tag back to an exact resolved source witness;
4. validate the union of all cell dependency roots;
5. reject cycles, unknown references and dormant witnesses;
6. evaluate every cell under the native scalar domain rules;
7. confirm every cell domain against the full sealed schema;
8. confirm the selected ordinal/domain contract;
9. only then materialize the selected scalar into the compatibility backend.

Tampering with an unselected cell therefore invalidates the projection too.

## Backend boundary

Only the selected canonical `whole`, `truth` or `glyphs` scalar crosses the projection frontend boundary. The compatibility program returns that literal directly.

The backend receives no schema id, source witness identity, storage locator or source-level projection name.

## Bounds

Projection inherits Native Cell Reality bounds:

- at most 4096 source witnesses;
- at most 64 cells;
- native scalar source/glyph byte budgets;
- Object Space graph-secret byte ceiling.

The selected ordinal must be within the complete sealed cell schema.

## Non-claims

Projection v1 does not yet provide:

- source-level cell access syntax;
- multiple simultaneous projections into another reality;
- nested cell projection;
- dynamic/runtime ordinal selection;
- authority-bearing cells;
- JSON/HTTP/DB field mapping.

This slice is intentionally static and metadata-authoritative. Its purpose is to prove safe aggregate consumption before projection is wired into reusable inputs or external data boundaries.
