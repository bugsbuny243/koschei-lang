# V5 MIR schema 2: normalized control flow

Koschei lowers every successfully checked module graph into one sealed,
backend-independent `MirGraph`. Schema 2 adds normalized values, instructions,
basic blocks, and explicit terminators while preserving the schema 1 integrity
contract. `run`, `build`, and `emit-go` still require the MIR produced only after
integrity, Typed HIR, legacy semantic, and capability checks succeed.

```ks
fn main() {
    let mut value = 0
    while value < 3 {
        value = value + 1
    }

    if value == 3 {
        println(value)
    } else {
        println(0)
    }
}
```

The source above becomes explicit blocks: the entry jumps to a loop condition,
the condition branches to the body or exit, the body stores the new value and
jumps back, and the final `if` branches to two blocks that join before return.
Every block has exactly one terminator.

## Normalized core

Schema 2 currently normalizes:

- constants and identifier loads;
- immutable/mutable bindings and identifier stores;
- unary and binary operations;
- member access and calls;
- `return`;
- `if` / `else` branches;
- `while` condition, body, exit, and back-edge blocks.

Each produced value has a numeric MIR identity and a structural type. Control
flow uses explicit `jump`, `branch`, `return`, or `unreachable` terminators. The
seal validator rejects duplicate values, undefined value uses, duplicate block
identities, and branches or jumps to missing blocks.

## Explicit migration boundary

Unsupported constructs are never silently omitted. They appear as an
`ast_fallback` instruction carrying the source node kind, location, and inferred
type. `for`, aggregate literals, `match`, interpolation, and other constructs
will be removed from this fallback set in later waves. The JSON counters make
that remaining migration debt machine-visible.

This remains a transition architecture: normalized CFG is generated, validated,
and included in the seal, but the interpreter and Go adapter still execute the
immutable AST compatibility payload. Direct backend execution of MIR
instructions is the next gate.

## Inspecting the contract

```bash
ks mir src/main.ks
ks check --json src/main.ks
```

`ks mir` emits stable JSON containing:

- MIR schema version `2`;
- the deterministic SHA-256 fingerprint;
- dependency order and imports;
- function parameter and return contracts;
- normalized blocks, instructions, and terminators;
- per-function block, instruction, and `ast_fallback` counts;
- generic struct and enum parameters;
- counts of typed bindings and expressions.

`ks check --json` includes the same `mir_version` and `mir_fingerprint`, allowing
editors and CI systems to associate a successful check with the exact backend
input. The repository truth gate also requires the simple `hello` example to
have normalized blocks and zero fallbacks.

## Fail-closed seal

The fingerprint covers the full immutable AST, imports, contracts, Typed HIR
expression types, and normalized CFG. A backend receives no MIR when checking
fails. Starting a new check clears any previous graph, so a failed re-check
cannot reuse stale output. Module/import tables are read-only. A forged or stale
MIR, invalid block graph, or changed instruction stops with `KS5002` before
interpreter execution or native generation.

Absolute paths are deliberately excluded. Identical sources in two directories
produce the same identity, while a same-typed body or instruction edit changes
the seal.

## Next gate

The next wave makes one backend execute normalized blocks directly, starting
with constants, bindings, arithmetic, calls, branches, loops, and returns. Then
`ast_fallback` is eliminated construct by construct until both interpreter and
native generation consume only normalized MIR.
