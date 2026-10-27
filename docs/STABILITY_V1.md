# Koschei Stability Policy v1

Status: **proposed for 1.0 — awaiting the owner's approval** (readiness gate G5)

This policy says which parts of Koschei a user may build on, which may still
change, and how a change reaches users. It takes effect for a release when
the owner approves it and the version number reaches 1.0.0.

## Versions

Koschei uses `MAJOR.MINOR.PATCH`.

- **PATCH**: fixes only. A program that checks and runs keeps checking and
  running with the same output, unless it depended on a bug that this policy
  calls a fix (see below).
- **MINOR**: additions. New syntax, library functions, capabilities and
  diagnostics. Nothing stable is removed; something may be deprecated.
- **MAJOR**: may remove deprecated surface. Each removal is listed in the
  changelog with its replacement.

Pre-1.0 releases (`0.x`) make no promise beyond the changelog.

## Surfaces

### Stable

A program using only these keeps its meaning across 1.x:

- Syntax: `fn`, `pure fn`, `let`, `let mut`, `if`/`else`, `while`, `for`,
  `break`, `continue`, `return`, `struct`, `enum`, `match`, `import`,
  generics on functions, `or` in its three forms, interpolation.
- Types: `Int`, `Float`, `String`, `Bool`, `Void`, `Error`, `List<T>`,
  `Map<String, T>`, `Option<T>`, `Result<T, E>`, user structs and enums.
- Value rules: 64-bit Int with overflow as `KS3501` Error values, the value
  budget (`KS3502`), value semantics of lists and structs, `String.to_int`.
- The String and List members documented in the language guide.
- Capabilities: `SystemCaps`, `caps.input`, `caps.clock`, `caps.random`,
  `caps.disk`, `caps.env`, `caps.net` and their documented operations; the
  rules that roots cannot act, narrowed tokens cannot widen, and tokens move,
  cannot be stored in collections, cannot be compared and print as their type.
- Core Library modules `text`, `list`, `secure`.
- Diagnostic **codes** (`KSxxxx`) and their meaning.
- CLI commands `check`, `run`, `build`, `caps`, `fmt`, `explain`, `lock`.

### Experimental

May change in a minor release, with a changelog entry:

- Library universe modules: `captain_marvel`, `hela`, `strange`, `wanda`,
  `xandar`, `morag`.
- `caps.serve`, `caps.persist`, `caps.process`.
- Bounded queues, structured tasks, deterministic parallel map, decimal.
- The text of diagnostic and runtime messages (codes stay stable).
- `ks build` admission: what compiles natively grows; a program that compiles
  keeps the same output, but a program refused with `KS4004` today may compile
  tomorrow and never the other way round within 1.x.

### Internal

No compatibility promise; not for users:

- Every Python module under `koschei/` except the `ks` entry point, MIR and
  its versions, Typed HIR, the generated Go source, the native runtime, and
  every installer.
- Research and architecture documents (`KOSCHEI_*_V1.md` other than this
  policy and the readiness plan).

## Deprecation

A stable item is deprecated in a minor release: the changelog names the
replacement and the checker reports a warning. It is removed no earlier than
the next major release.

## What counts as a fix

A change is a fix, not a break, when the old behavior contradicted the
documented rule or differed between executors: for example, the struct
aliasing fix, `String.to_int` rejecting `1_000`, or a capability printing a
host memory address. Each such fix is called out in the changelog.

## Executors

`ks run` and a `ks build` binary must produce the same output and the same
Error values for every program `ks build` accepts. A difference is a bug of
the highest priority.
