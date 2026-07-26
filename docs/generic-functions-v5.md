# Generic functions in Koschei V5

Koschei generic functions keep everyday code compact while preserving one
structural contract across the checker, editor, interpreter and native backend.

```ks
fn identity<T>(value: T) -> T {
    return value
}

fn head_or<T>(values: List<T>, fallback: T) -> T {
    return values.get(0) or fallback
}
```

Calls do not need explicit type arguments:

```ks
let number = identity(42)                 // T = Int
let name = head_or(["Ada"], "unknown")   // T = String
```

## Inference contract

Type variables are inferred from function arguments and substituted through
nested `List`, `Map`, `Option`, `Result` and union types. Multiple parameters are
supported:

```ks
fn choose_left<T, U>(left: T, right: U) -> T {
    return left
}
```

Repeated evidence must agree. `same(1, "two")` for a function whose two
parameters are both `T` fails with `KS1307`. A type variable used only in a
return position also fails because the caller provides no evidence from which to
infer it. Koschei never silently falls back to `Any` or a hidden dynamic type.

Generic signatures remain intact across module boundaries. The Typed HIR owns
inference; a deterministic compatibility specialization lets the older semantic
pass continue checking scope, immutability, error handling and capability rules
without changing runtime syntax.

## Security boundary

An unconstrained `T` cannot currently bind to a capability-bearing type. This is
a deliberate fail-closed rule: capability generics require explicit effect and
authority constraints before they can be safe. Until that layer exists, calls
such as `identity(net_token)` fail with `KS2402`.

## Current boundary

This slice supports inferred generic **functions**. It does not yet add:

- explicit call-site type arguments;
- generic structs or user-defined generic enums;
- trait or interface constraints;
- effect/capability type parameters;
- generic recursion through another unresolved generic call;
- backend-independent MIR monomorphization.

The existing collection runtime keeps its legacy `get`/`or` ABI. Generic
`Option<T>` and `Result<T, E>` values created with `Some`, `None`, `Ok` and `Err`
are supported, while a full collection-access ABI cleanup remains a later V5
gate.
