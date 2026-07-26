# Typed collections in Koschei V5

Typed collections make the element contract visible while keeping literals
compact and inferred.

```ks
fn names() -> List<String> {
    return ["Ada", "Lin"]
}

fn count(config: Map<String, Int>) -> Int {
    return config.get("count") or 0
}
```

## Supported positions

`List<T>` and `Map<String, V>` are accepted in:

- function parameters and return types;
- struct fields;
- enum payloads;
- imported module APIs;
- nested combinations such as `List<Map<String, Int>>`.

A literal is checked against the declared contract. Passing `[1, "two"]` to a
`List<Int>` parameter fails before execution. A `for` binding receives `T`, so
methods and operators are checked against the actual element type.

## Compatibility and safety

Raw `List` and `Map` remain accepted as temporary compatibility wildcards for
v0.9 programs. New code should use explicit contracts at API boundaries and
rely on inference for local literals.

Map keys are currently fixed to `String`. Capability-bearing values are not
valid container arguments: `List<NetCaps>` and `Map<String, DiskCaps>` fail
closed because authority must remain explicit and directly traceable.
