# V5 MIR schema 3: effects and static resource shape

Koschei lowers every successfully checked module graph into one sealed,
backend-independent `MirGraph`. Schema 2 added normalized values, instructions,
basic blocks, and explicit terminators. Schema 3 keeps that control-flow contract
and adds deterministic capability-effect and static resource summaries. `run`,
`build`, and `emit-go` still require the MIR produced only after integrity, Typed
HIR, legacy semantic, and capability checks succeed.

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

The current MIR normalizes:

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

## Capability effects

Every MIR function records deterministic `calls` and `effects` tuples. Direct
capability operations such as `disk.read`, `disk.write`, `env.read`, and network
access are inferred from the checked body. Effects then propagate through local
calls to a fixpoint, including recursive call graphs. Seal validation re-runs the
analysis, so changing an effect or call edge without rebuilding MIR fails with
`KS5002`.

## Static resource shape

Schema 3 adds one sealed `resources` object per function:

- `basic_blocks` — normalized block count;
- `instructions` — normalized instruction count;
- `ast_fallbacks` — constructs still using the transition bridge;
- `backward_edges` — loop-shaped CFG edges whose target is an earlier block;
- `self_recursive` — whether the function directly calls itself.

These values are not runtime quotas and are not presented as exact complexity
proofs. They are a deterministic static shape that later resource policies can
consume. The summary is included in the fingerprint and independently derived
again by `assert_sealed`; forged counts or recursion flags are rejected before an
interpreter or native backend runs.

## Explicit migration boundary

Unsupported constructs are never silently omitted. They appear as an
`ast_fallback` instruction carrying the source node kind, location, and inferred
type. `for`, aggregate literals, `match`, interpolation, and other constructs
will be removed from this fallback set in later waves. The JSON counters and
resource summary make that remaining migration debt machine-visible.

This remains a transition architecture: normalized CFG is generated, validated,
and included in the seal, but the interpreter and Go adapter still execute the
immutable AST compatibility payload. Direct backend execution of MIR
instructions and enforceable runtime budgets remain later gates.

## Inspecting the contract

```bash
ks mir src/main.ks
ks check --json src/main.ks
```

`ks mir` emits stable JSON containing:

- MIR schema version `3`;
- the deterministic SHA-256 fingerprint;
- dependency order and imports;
- function parameter and return contracts;
- local calls and transitive capability effects;
- normalized blocks, instructions, and terminators;
- the sealed static resource summary;
- generic struct and enum parameters;
- counts of typed bindings and expressions.

`ks check --json` includes the same `mir_version` and `mir_fingerprint`, allowing
editors and CI systems to associate a successful check with the exact backend
input. The repository truth gate requires the simple `hello` example to have
normalized blocks, zero fallbacks, and a resource summary matching its CFG.

## Fail-closed seal

The fingerprint covers the full immutable AST, imports, contracts, Typed HIR
expression types, capability effects, normalized CFG, and static resource shape.
A backend receives no MIR when checking fails. Starting a new check clears any
previous graph, so a failed re-check cannot reuse stale output. Module/import
tables are read-only. A forged or stale MIR, invalid block graph, changed effect,
changed instruction, or changed resource summary stops with `KS5002` before
interpreter execution or native generation.

Absolute paths are deliberately excluded. Identical sources in two directories
produce the same identity, while a same-typed body or instruction edit changes
the seal.

## Next gate

The next wave turns static shape into enforceable policy: user-visible resource
budgets, transitive call-graph cost summaries, and runtime counters that fail
closed. In parallel, one backend begins executing normalized blocks directly so
`ast_fallback` can be eliminated construct by construct.
