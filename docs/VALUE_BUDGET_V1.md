# Koschei Value Budget v1 (Titan)

Status: **language rule in every executor; `KS3502`**

Titan is the planet of the library universe that bounds growth (see
`KOSCHEI_KUTUPHANE_EVRENLERI_V1.md`). Its first rule bounds the size of each
value.

## Rule

| Value | Bound |
|---|---|
| `String` | at most 16,777,216 bytes of UTF-8 (16 MiB) |
| `List` | at most 1,048,576 items |

An operation that would build a larger value produces a `KS3502` Error value
instead, the same way Int overflow produces `KS3501`. The Error flows like any
other: arithmetic propagates it, `or` catches it, and an Error that reaches a
typed boundary stops the program.

```ks
fn main() {
    let mut text = "a"
    let mut round = 0
    while round < 25 {
        text = text + text
        round = round + 1
    }
    let safe = text or "too large"
    println(safe)
}
```

The bound counts bytes, not characters: `"ç"` repeated 2^23 times is exactly
16 MiB; one more `"ç"` is over.

## Where it is checked

| Operation | Check |
|---|---|
| String `+` | the result |
| interpolation `"{a}{b}"` | the result |
| `String.join` | before joining: items plus the separator between them |
| `String.split` | before splitting: the number of pieces |
| `List.push` | before pushing |
| other String/List members (interpreter only: `sort`, `flatten`, …) | the result |
| `disk.read` | reads at most one character past the bound; a larger file is `KS3502` |

`join`, `split` and `push` check first because they can turn a small input
into a large value: a 16 KiB separator between 1,026 empty items is already
over the bound. `+` and interpolation check their result; the transient value
is at most twice the bound, or the size of values that already exist.

HTTP responses keep their smaller bound (`http_response_budget_v1`, 1 MiB).

## Same point, same message

The checked-AST interpreter, the canonical MIR executor, the direct MIR
runtime and MIR-Go binaries stop at the same operation and print the same
message. `tests/test_value_budget_v1.py` runs programs exactly on each bound
and one step past it in all four.

## Host memory

The rule bounds each value, not the sum of all values. When many values that
each fit exhaust the host's memory:

- `ks run` stops with `KS3502` and exit status 1. It used to end with a raw
  Python `MemoryError` traceback.
- A MIR-Go binary stops with the Go runtime's `fatal error: out of memory`
  and exit status 2. Go cannot turn that fatal error into a Koschei
  diagnostic.

Neither executor reuses half-built state after exhaustion, because the
process stops. A budget for total live memory is the next Titan step.

## Not covered yet

- Total live memory, as above.
- `Map` values, which MIR-Go does not compile yet, have no entry bound.
- The step budget (`KS3601`) still bounds `ks run` time; binaries are not
  metered.
