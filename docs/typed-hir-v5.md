# V5 Typed HIR — Migration Slices 1–2

Koschei v0.9 historically carried types as strings such as `Option<Int>` and
`String or Error`. The V5 migration introduces immutable structural type nodes
without breaking the current runtime ABI.

## Structural nodes

- `NamedType("Int")`
- `GenericType("List", (NamedType("Int"),))`
- `UnionType((NamedType("Int"), NamedType("String")))`
- `UnknownType()` for evidence the current slice cannot yet prove

Nested generics and unions are parsed once by `koschei.type_system`; later
passes no longer need their own comma/angle-bracket string splitting.

## Typed HIR evidence

`koschei.typed_hir` records types for local bindings and expressions. It
infers:

- `[1, 2, 3]` as `List<Int>`;
- `{ "name": "Ada" }` as `Map<String, String>`;
- `list.get(0)` as `Option<T>`;
- `value or fallback` as the narrowed success type;
- a `for value in list` binding as the list's element type.

Heterogeneous collections become structural unions. An operation must be valid
for every possible member; unsafe operations fail with `KS1306` before
interpreter or native code generation.

## Public collection contracts

Migration slice 2 exposes typed collections in normal Koschei source:

```ks
struct Batch {
    ids: List<Int>,
}

fn total(values: List<Int>) -> Int {
    let mut sum = 0
    for value in values {
        sum = sum + value
    }
    return sum
}

fn port(config: Map<String, Int>) -> Int {
    return config.get("port") or 8080
}
```

The contract is enforced for function arguments and returns, struct fields,
enum payloads and imported module APIs. `Map` keys remain `String` in this
runtime generation. Raw `List` and `Map` annotations remain temporary v0.9
compatibility wildcards.

Capability values cannot be hidden inside `List`, `Map`, `Option` or `Result`.
The Typed HIR validates the original structural contract, then a compatibility
view erases collection arguments only for the old v0.9 semantic pass. The
interpreter and native backend still receive the original program.

## Deliberate boundary

User-defined generic functions and structs, type parameters, traits, effect
parameters and backend-independent MIR remain future V5 gates. The next slice
moves from built-in generic containers to declared type parameters without
weakening capability containment.
