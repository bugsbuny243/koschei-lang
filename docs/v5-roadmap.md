# Koschei V5 Engineering Principle

Koschei targets two goals at the same time:

1. Security beyond Rust's memory-safety boundary through capability, effect,
   dependency, resource and runtime-isolation guarantees.
2. A daily writing experience simpler than Python through inference, safe
   defaults, compact syntax and actionable diagnostics.

## Non-negotiable order

1. Security
2. Understandability
3. Ease of writing
4. Predictable behaviour
5. Performance
6. Advanced flexibility

## V5 gates

- Typed HIR and structural Type AST
- Typed collections and generics
- Capability/effect flow as part of the type contract
- Sealed backend-independent MIR foundation (landed); normalized instructions, basic blocks and direct backend consumption remain open
- Deterministic ownership/region memory model
- Signed, capability-declared dependency ecosystem
- Self-hosted and reproducibly bootstrapped compiler
- Linux, macOS, Windows and WASM production targets
- Independent security review, fuzzing and compatibility guarantees

A feature is not complete merely because it parses. It must preserve the same
meaning and security contract in the interpreter, native backends and tooling.
