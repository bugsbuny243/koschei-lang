# Koschei Native Identity

Koschei is an original programming language. It is not a Python dialect, a Go transpiler, a Rust clone, or a syntax skin over another host language.

## Non-negotiable rule

Koschei owns its semantics.

The following are defined by Koschei specifications and implementations, not inherited from another language:

- source syntax and grammar;
- type semantics;
- capability and authority model;
- ownership, affine and typestate rules;
- error and diagnostic model;
- module/package semantics;
- concurrency and resource semantics;
- interpreter/runtime behavior;
- canonical IR and verification rules;
- source-protection and Trust Plane gates.

A foreign backend may exist only as an adapter behind a stable Koschei-owned contract. It must not become the source of truth for language behavior.

## Architecture direction

The canonical execution path is:

```text
Koschei source
    -> Koschei parser
    -> Koschei typed HIR
    -> Koschei verified MIR
    -> Koschei runtime / native execution contract
```

Foreign targets such as Go, C, WASM or another platform are optional interoperability targets. They are downstream adapters and are never allowed to redefine Koschei semantics.

## Design test

For every proposed feature, ask:

1. Can the behavior be specified without mentioning another programming language?
2. Can the interpreter/runtime test the behavior directly from Koschei semantics?
3. Does capability enforcement remain identical regardless of backend?
4. Would replacing every foreign backend leave the language definition unchanged?

If any answer is no, the feature is not ready for the canonical language path.

## Originality boundary

Koschei may study other languages for failure modes, ergonomics and interoperability constraints. It does not copy their grammar or import their semantics as shortcuts.

The project target remains: a capability-secure language with its own identity, easier to use than systems languages while enforcing substantially stronger default authority boundaries.
