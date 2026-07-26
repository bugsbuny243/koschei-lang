# V5 Typed HIR — Migration Slice 1

Koschei v0.9 historically carried types as strings such as `Option<Int>` and
`String or Error`. V5 migration slice 1 introduces immutable structural type
nodes without breaking the current surface AST or runtime ABI.

## Structural nodes

- `NamedType("Int")`
- `GenericType("List", (NamedType("Int"),))`
- `UnionType((NamedType("Int"), NamedType("String")))`
- `UnknownType()` for evidence the current slice cannot yet prove

Nested generics and unions are parsed once by `koschei.type_system`; later
passes no longer need their own comma/angle-bracket string splitting.

## Typed HIR evidence

`koschei.typed_hir` now records types for local bindings and expressions. It
infers:

- `[1, 2, 3]` as `List<Int>`;
- `{ "name": "Ada" }` as `Map<String, String>`;
- `list.get(0)` as `Option<T>`;
- `value or fallback` as the narrowed success type;
- a `for value in list` binding as the list's element type.

Heterogeneous collections remain source-compatible during migration and become
structural unions. An operation must be valid for every possible member; unsafe
operations fail with `KS1306` before interpreter or native code generation.

## Deliberate boundary

This slice does **not** yet expose user-authored `List<T>` / `Map<K,V>`
annotations, generic functions, or a backend MIR. Those remain the next V5
migration gates. The new pass runs alongside the v0.9 semantic checker so
existing programs and the capability ABI stay stable while type evidence moves
to the new representation.
