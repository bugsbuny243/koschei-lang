# V5 interpreter runtime budgets

`ks run` executes sealed MIR through a fail-closed interpreter budget. Every run
has a statement/expression step budget and a simultaneous Koschei call-frame
budget:

```bash
ks run src/main.ks --max-steps 200000 --max-call-depth 64
```

The secure defaults are 1,000,000 dynamic steps and 512 call frames. A run that
exhausts its step fuel stops with `KS3601`; a run that exceeds the selected call
budget stops with `KS3602`. The 512-frame value is also a hard language safety
ceiling, so the user cannot raise the interpreter above it.

```ks
fn descend(value: Int) -> Int {
    if value == 0 {
        return 0
    }
    return descend(value - 1)
}

fn main() {
    let mut value = 4
    while value > 0 {
        value = value - 1
    }
    println(descend(4))
    println("runtime budget ready")
}
```

The meter counts statements and expression evaluations, including every loop
condition. Therefore an empty `while true {}` cannot evade the budget. Call depth
includes `main`, local functions, imported functions, and calls made by collection
helpers such as `List.filter`.

## Honest boundary

This wave enforces budgets for the interpreter path used by `ks run`. Native
binaries produced by `ks build` still have the existing hard recursion defense but
do not yet accept the user-selected step budget. The CLI and documentation do not
claim native budget parity until the Go backend consumes the same runtime policy.
Static MIR resource summaries remain useful policy input, but they are not exact
complexity proofs and do not replace dynamic metering.
