# Direct MIR Modules v1

Direct MIR execution is the AST-free execution path for Koschei's normalized MIR.
This contract extends that path across authenticated module-graph identities instead
of treating a multi-module program as an automatic compatibility fallback.

## Supported v1 module behavior

For a sealed, checked `MirGraph`, the direct executor may:

- resolve a local function only inside the currently executing MIR module;
- resolve an import alias to the exact target module key already sealed in the MIR graph;
- resolve `imported_module.function` to a function reference bound to that target module key;
- execute transitive imported calls while preserving each module's own local namespace;
- keep one global step budget and one call-depth budget across the complete graph.

A function reference therefore carries semantic module identity plus function name.
The physical source path is not re-resolved during a call.

## Fail-closed boundary

This slice does **not** make arbitrary member access native-MIR executable.

A `MirMember` instruction is accepted by the support inspector only when its receiver
is a direct import alias and the member is a function present in the sealed target
module. List/String methods, struct fields and other value-member forms remain
unsupported until they have their own normalized runtime contract.

Structs, enums, AST fallbacks and operators outside the current direct-MIR allowlist
also remain rejected before execution.

## Acceptance evidence

The regression suite requires both:

1. a transitive three-module program with colliding local function names to execute
   from MIR blocks and produce the imported module's result; and
2. the production-reference scale harness to execute a 32-realm / 64-function
   transitive workspace directly through `run_mir_native()` and produce `32`.

The existing locked workspace runner still uses the compatibility tree-walking
runtime over sealed MIR payloads. This change does not relabel that path as direct
MIR; it creates an explicit second execution gate so migration can be measured.

## Non-claims

Passing this contract does not mean the complete production reference is already
AST-free. JSON fallible handling, general value members and other constructs still
need normalized MIR coverage before the twelve-realm reference can move wholly to
the direct executor.
