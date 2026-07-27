# V5 sealed MIR foundation

Koschei now lowers every successfully checked module graph into one sealed,
backend-independent `MirGraph`. The interpreter and Go native adapter no longer
accept a freshly loaded, unchecked module graph from the CLI; `run`, `build`, and
`emit-go` require the MIR produced after integrity, Typed HIR, legacy semantic,
and capability checks have all succeeded.

```ks
struct Box<T> {
    value: T,
}

fn answer(box: Box<Int>) -> Int {
    return box.value + 1
}

fn main() {
    println(answer(Box { value: 41 }))
}
```

The program is checked once. Its functions, aggregate declarations, imports,
full AST body, and Typed HIR expression contracts are then hashed into a
path-independent SHA-256 fingerprint. Both execution paths consume the same
sealed graph.

## Inspecting the contract

```bash
ks mir src/main.ks
ks check --json src/main.ks
```

`ks mir` emits stable JSON containing:

- the MIR schema version;
- the deterministic fingerprint;
- dependency order and imports;
- function parameter and return contracts;
- generic struct and enum parameters;
- counts of typed bindings and expressions.

`ks check --json` includes the same `mir_version` and `mir_fingerprint`, allowing
editors and CI systems to associate a successful check with the exact backend
input.

## Fail-closed seal

A backend receives no MIR when checking fails. Starting a new check first clears
any previous graph, so a failed re-check cannot accidentally reuse stale output.
The module and import tables exposed by MIR are read-only. If a forged or stale
MIR carries a fingerprint that does not match its full program contract, Koschei
stops with `KS5002` before interpreter execution or native code generation.

The fingerprint deliberately excludes absolute file-system paths. Identical
sources in two directories produce the same identity, while even a same-typed
body edit such as `41` to `42` produces a different seal.

## Current boundary

This is the **MIR foundation**, not the final optimizing IR. The first schema
still carries immutable AST declarations as executable payloads, paired with the
structural types from Typed HIR. Small adapters feed those checked payloads to
the current interpreter and Go generator.

The next MIR wave replaces statement and expression payloads incrementally with:

1. normalized MIR values and instructions;
2. explicit basic blocks and terminators;
3. a typed call graph and monomorphized generic instances;
4. capability/effect facts attached to calls;
5. backend consumption of MIR nodes without AST fallback.

Keeping this boundary explicit prevents a migration bridge from being advertised
as the completed V5 backend architecture.
