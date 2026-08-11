# Effect Contracts v1

Koschei's first mandatory source-level effect contract is `pure fn`.

`pure` is not documentation. It is a compiler-enforced promise that the function
and its transitive direct call graph produce no observable authority, I/O,
shared-state, task-scheduling, or unknown-call effect.

## Pure computation

```ks
pure fn fee(notional: Int, bps: Int) -> Int {
    return notional * bps / 10000
}

pure fn normalize(symbol: String) -> String {
    return symbol.trim()
}

fn main() {
    println(fee(1000000, 5))
    println(normalize("  KOSCHEI  "))
}
```

The `println` calls are outside the pure functions. Local arithmetic and the
immutable String operation remain effect-free.

## Transitive enforcement

A pure function cannot hide an effect behind a helper:

<!-- verify: skip — intentional KS3940 counter-example -->
```ks
fn audit(value: Int) -> Int {
    println(value)
    return value
}

pure fn calculate(value: Int) -> Int {
    return audit(value)
}
```

`calculate` is rejected with `KS3940` because `audit` has `console.write` in its
transitive effect set.

The same rule crosses module boundaries. Imported functions are analyzed before
the importing module because the module graph is processed in dependency order.

## Authority is an effect boundary

A pure function cannot accept or return capability-bearing authority, even if it
never performs I/O. The contract therefore cannot be used to launder authority
through an apparently harmless API.

<!-- verify: skip — intentional KS3940 counter-example -->
```ks
pure fn fake_pure(authority: NetCaps) -> Int {
    return 1
}
```

Authority derivation (`allow` / `allow_read_only`) and narrowed capability
operations are effectful as well.

## V1 effect names

The first stable effect vocabulary includes:

- `authority.input`
- `authority.output`
- `authority.derive`
- `console.write`
- `net.io`
- `disk.read`
- `disk.write`
- `env.read`
- `process.exec`
- `shared-memory.queue`
- `concurrency.task`
- fail-closed `unknown.*` effects for calls the compiler cannot prove safe

`parallel_map` is treated as a deterministic computation primitive only because
its existing contract restricts the worker and commits results/failures by input
index rather than scheduler completion order. Its worker is included in the
transitive call graph.

## Fail-closed unknown calls

V1 does not infer purity from optimism. An indirect or unknown call inside a
`pure fn` is an effect and compilation stops. Later function/effect types may
make more higher-order programs provably pure without weakening this default.

`List.filter` remains outside pure v1 because its callback effect is not yet
represented in a first-class function/effect type.

## What v1 does not claim

This is the first A1 slice, not the complete effect system.

Still required:

- explicit non-pure effect-set contracts for public APIs;
- effect polymorphism for higher-order/generic functions;
- package compatibility rules that reject effect widening;
- effect-aware FFI signatures;
- effect manifests bound into release/build policy.

The invariant established here is smaller but hard: **if source says `pure`, an
observable or unknown effect makes the program fail compilation.**
