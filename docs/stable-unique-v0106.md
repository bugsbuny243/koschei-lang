# Stable `List.unique()` — v0.10.6

`List<T>.unique() -> List<T>` returns a new list containing the first occurrence
of each structurally equal value.

## Contract

- Source order is preserved.
- The input list is not mutated.
- Equality is Koschei structural equality, not host hashing.
- Nested lists, maps, enums and structs are supported when their values are
  otherwise valid Koschei data.
- Capability-bearing values remain forbidden and are rejected defensively at
  runtime.
- Interpreter and generated Go code must produce identical results.

```ks
let values = ["a", "b", "a", "c", "b"]
println(values.unique())
// ["a", "b", "c"]
```

The implementation is intentionally deterministic and uses a stable linear
scan. A future optimized representation may change complexity only if it keeps
the same structural equality and ordering contract.
