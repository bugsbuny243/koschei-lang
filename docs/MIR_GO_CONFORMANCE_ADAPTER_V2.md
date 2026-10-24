# MIR-Go Conformance Adapter v2

Status: **host conformance adapter; bootstrap evidence only**

`koschei/mir_go_native.py` projects a sealed MIR v4 graph into Go for
`ks build`. Under the [native execution boundary](../KOSCHEI_NATIVE_EXECUTION_BOUNDARY_V1.md)
it is a host conformance adapter, not a Koschei-native runtime and not a
semantic authority. v2 changes what the adapter computes, not who owns the
meaning: every rule it applies is copied from the canonical sealed-MIR
executor (`koschei/mir_executor_v1.py`) and the canonical renderer
(`interpreter.ks_to_string`).

## Why v2

v1 emitted statically typed Go and so imported Go's own meaning into Koschei
programs:

| Program | `ks run` | v1 native |
|---|---|---|
| `println(3.0)` | `3.0` | `3` |
| `println(1000000.0)` | `1000000.0` | `1e+06` |
| `3037000500 * 3037000500` returned from an `Int` function | runtime error, exit 1 | `-9223372036709301616`, exit 0 |

The last row is a silent signed-overflow wrap in a released binary. v1 also
could not compile `List<T>`, method calls, `for` loops, generic functions,
imported modules or `or` forms, so no Core Library program could be built.

## Value model

Each MIR slot holds a Go `any`:

| Koschei | Go |
|---|---|
| `Int`, `Float`, `String`, `Bool` | `int64`, `float64`, `string`, `bool` |
| `List<T>` | `[]any`, never mutated after construction |
| `Option`, `Result`, user enums | `_ksEnumValue` (owner, variant, payload, type evidence) |
| runtime `Error` | `_ksError`, which flows as a value exactly like `KsError` |
| `Void` | `_ksUnit` |

Because errors are values, the binary reproduces the executor's error flow:
Int overflow, division by zero and failed String/List operations produce
Error values; arithmetic propagates them; `or` forms catch them; an `if`
whose condition is an Error runs neither arm (sealed MIR guards it with
`MirIsRuntimeError`); an Error that reaches a typed call boundary stops the
program with exit status 1.

Runtime type evidence is checked at every call boundary with a port of the
executor's matcher, including generic type-parameter binding. The call-depth
limit (512, `KS3105`) is enforced. The interpreter's step budget is a `ks run`
policy, not program semantics, and is not applied to binaries.

## Admitted subset

Admitted: scalars and their operators, `List<T>`, `for`/`while`/`break`/
`continue`, `if`/`match`, `Option`/`Result`/user enums, `or return`/
`or value`/`or { }`, string interpolation, generic functions, imported modules
(local siblings and the Core Library), `print`/`println`/`Error`, and the
members `String.length/contains/trim/split/join` and
`List.length/get/push/contains/take`.

Fails closed with `KS4004`: structs, `Map`, capabilities and capability-typed
signatures, callback members (`filter`, `map`, `sort`, …), `to_int`/
`to_float`, function or constructor values, and any instruction outside the
list above. The legacy AST-Go backend is never used as a fallback.

## Evidence

- `tests/test_mir_go_native_v2_parity.py` builds programs with `ks build` and
  requires byte-identical standard output and the same success/failure as
  both `ks run` and the budgeted canonical executor: Int boundaries and
  errors, 71 Float values, Unicode strings, nested lists, enums and `or`
  forms, the Core Library, local modules, stopping paths, the depth limit,
  fail-closed constructs and the linked host symbols.
- A wider development corpus of 82 programs (the Core Library differential
  programs, 64 `ks-differential-fuzz` programs over four seeds, and Int,
  Float, string, list, enum, control-flow and error-path probes) matched the
  canonical executor in all 82 cases. Against `ks run`, those programs plus
  the 6 admitted repository examples and 6 call-depth programs (each
  executor lane at and beyond the 512 limit) matched in all 94 cases,
  including exit status.
- Binaries link no filesystem, socket, environment, process or network
  symbols beyond what `fmt` already brought into v1 binaries.

This is bootstrap evidence in the sense of the boundary's evidence rule. It
shows that the Go projection agrees with the canonical executor; it is not
evidence of a Koschei-native executor.

## One executor rule for `ks run` and `ks build`

`ks run` sends every sealed graph without a `MirAstFallback` to sealed MIR:
the direct MIR runtime when it admits the graph, otherwise the canonical MIR
executor. The checked-AST compatibility interpreter is kept only for graphs
that still carry an AST migration boundary; no repository example or
benchmark program reaches it. Before this rule, programs with member calls
but no Option/Result/enum facts ran on the AST interpreter, which replaced a
list literal containing an Error with the Error itself while sealed MIR keeps
it as an element (`tests/test_runtime_single_authority_v1.py`).

`ks run` also gives the host interpreter enough recursion headroom to reach
the language limit: every lane runs 512 nested calls and stops beyond them
with `KS3602`/`KS3105`, where it used to crash with a Python `RecursionError`
after roughly 100.

## Known differences

- Programs above the interpreter step budget stop under `ks run` and run to
  completion natively.
- Very large single functions build slowly: a generated 2,300-line `main`
  takes about 17 seconds in `go build`.
