# Numeric List reductions — v0.10.5 slice

Koschei exposes three deterministic numeric reductions:

```ks
let values = [4, 8, 15, 16, 23, 42]
let total = values.sum() or 0
let minimum = values.min() or 0
let maximum = values.max() or 0
```

## Static contracts

- `List<Int>.sum() -> Result<Int, Error>`
- `List<Int>.min() -> Result<Int, Error>`
- `List<Int>.max() -> Result<Int, Error>`
- `List<Float>.sum() -> Result<Float, Error>`
- `List<Float>.min() -> Result<Float, Error>`
- `List<Float>.max() -> Result<Float, Error>`

The element type must be statically proven. `List<String>`, an untyped empty list,
mixed numeric unions, and unresolved generic element types are rejected with
`KS1306` instead of being guessed.

## Why the result is fallible

A runtime list does not carry a trusted generic type tag when it is empty. In
addition, Int summation may leave the signed 64-bit range and Float values may
be NaN or Infinity. Returning `Result<T, Error>` keeps all of those cases
explicit and lets normal Koschei `or` handling choose a fallback.

## Runtime defenses

Interpreter and native Go execution both:

- reject empty reductions as an error value;
- reject mixed or non-numeric runtime elements;
- reject NaN and Infinity;
- detect signed 64-bit Int overflow during `sum()`;
- reject capability-bearing lists;
- preserve identical output between interpreter and native execution.

No mutation, authority widening, implicit numeric promotion, or benchmark-only
syntax is introduced.
