# Koschei Surface Runtime v1

Koschei Surface is the browser/UI execution profile for Koschei Lang. It exists so Koschei applications do not need application-authored JavaScript.

## Goal

Source remains `.ks`. UI logic, animation, input handling, state projection, and Universe rendering are expressed in Koschei semantics and compiled into a deterministic Surface Program.

## Execution targets

1. **Native Surface VM** — zero JavaScript. Runs on desktop/mobile with a native renderer backend.
2. **Web Surface VM** — Surface Program executes in WebAssembly. A minimal audited host bootstrap may be required by current browsers to instantiate the Wasm module and expose graphics/input host calls. Application code never becomes JavaScript and the bootstrap is not an authority source.
3. **Headless Surface VM** — deterministic rendering/test backend for CI and snapshot verification.

## Non-negotiable laws

- No `eval`, dynamic code generation, ambient DOM access, dynamic import, prototype mutation, global object access, or arbitrary network access.
- Surface programs are capability-bound. Rendering, input, clock, network-observer and storage-observer are explicit host capabilities.
- UI code cannot mint Koschei authority.
- Runtime state consumed by Universe must remain authenticated and authority-free.
- Deterministic mode uses logical time and canonical input events.
- Surface bytecode has a digest and version; unknown opcodes fail closed.
- Native and Web targets must produce equivalent logical render commands for equivalent canonical input.

## Architecture

`.ks source -> Koschei parser/typechecker -> Surface lowering -> KSP1 bytecode -> Surface VM -> render command stream -> native/Wasm host`

The VM does not expose a general object model like JavaScript. Values are closed algebraic types: integers, booleans, bounded text, vectors, records, enums, handles, and immutable collections. Mutable state exists only in declared Surface cells.

## Initial host capability set

- `surface.draw` — append bounded render commands.
- `surface.input` — receive canonical pointer/key/touch events.
- `surface.clock` — logical monotonic frame time only.
- `surface.observer` — read authenticated authority-free Universe snapshots.
- `surface.font` — select registered font handles; no filesystem access.

Network, filesystem, process execution, clipboard, camera, microphone, location, and arbitrary browser APIs are absent by default.

## Universe migration

Current handwritten JavaScript renderer is transitional. Migration order:

1. Freeze render/input behavior as Surface operations.
2. Compile Universe effects (planets, portals, forces, pan/zoom) into KSP1.
3. Run KSP1 in the native/headless VM and compare render-command digests.
4. Add Wasm Surface VM host for web use.
5. Remove application-authored JavaScript from Universe.

The final web artifact may contain only an audited fixed bootstrap required by the browser host; all product behavior remains Koschei bytecode/Wasm.