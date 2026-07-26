# V5 runtime and type-contract alignment

Typed HIR and the defensive runtime must describe the same language. This gate
closes two places where v0.9 accepted a program statically but interpreted it
with a different contract.

## Structural collection checks at runtime

`List<T>` and `Map<String, V>` are now recursively understood by the interpreter
runtime, including nested forms such as:

```ks
fn first_port(rows: List<Map<String, Int>>) -> Int {
    let fallback = {"port": 0}
    let row = rows.get(0) or fallback
    return row.get("port") or 0
}
```

Function parameters and returns are checked element by element. Raw `List` and
`Map` remain temporary v0.9 compatibility wildcards, but typed APIs no longer
fall back to the raw form at execution time.

## Error classification

`KS3401` is reserved for capability type-integrity violations: an authority
value was disguised, contained or passed through a contract that must not carry
it.

An ordinary defensive runtime type mismatch is `KS3106`. It explicitly says
that the failure is not a capability attack. This keeps security telemetry
credible and prevents normal application bugs from being mislabeled as an
authority-laundering attempt.

## Division contract

Numeric division now follows one deterministic rule in the interpreter and Go
native backend:

- `Int / Int -> Int`, truncated toward zero;
- `Float / Float -> Float`;
- division by zero remains an error value;
- `Int.MIN / -1` reports checked overflow (`KS3501`).

Therefore `125 * 20 / 100` is the `Int` value `25`, and `-5 / 2` is `-2` on
both execution paths. This matches the static arithmetic type contract instead
of producing a hidden Float at runtime.

## Migration boundary

The alignment currently lives in a small explicit bridge. It patches the v0.9
runtime from the shared structural type model and is covered by interpreter and
native parity tests. The bridge is deleted when the interpreter and native
runtime consume Typed HIR directly.
