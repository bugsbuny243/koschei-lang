# Koschei v0.10 language ergonomics

v0.10 is deliberately a language-surface release. It does not advance the native parser, Data ABI, runtime budgets, region memory, lambdas, traits, or `impl` blocks.

## Integer remainder

`%` has the same precedence as `*` and `/` and is defined only for `Int % Int`.

```ks
fn main() {
    println("{10 % 3}")   // 1
    println("{-5 % 3}")   // -2
}
```

Integer division truncates toward zero. Remainder preserves:

```text
a == (a / b) * b + (a % b)
```

A zero divisor is a runtime error value, consistent with `/`. Float remainder is rejected with `KS1301`.

## Loop control

```ks
for value in [1, 2, 3, 4] {
    if value == 2 { continue }
    if value == 4 { break }
    println("{value}")
}
```

`break` and `continue` target the nearest `for` or `while`. Outside a loop they are rejected with `KS1901`. Labelled loop control remains a future feature.

## Optional local annotations

```ks
let count: Int = 5
let mut names: List<String> = ["Ada", "Lin"]
let config: Map<String, Int> = {"port": 8080}
```

Annotations are optional. Inference remains the default. When an annotation is present, a mismatch is rejected with `KS1301` and reports both the expected and inferred type.

## Block-bodied match arms

```ks
let result: Int = match Some(4) {
    Some(value) => {
        println("found")
        value + 1
    }
    None => {
        0
    }
}
```

The final expression is the block result. A block without a tail expression has type `Void`. `return` exits the enclosing function. Exhaustiveness remains mandatory.

After `=>`, `{ ... }` is always a block. Use parentheses when a Map literal must be the arm expression:

```ks
Some(value) => ({"value": value})
```

## Direct struct field mutation

```ks
struct Counter { value: Int }

fn main() {
    let mut counter = Counter { value: 0 }
    counter.value = 1
}
```

Only a directly bound struct declared with `let mut` may be changed. Immutable bindings are rejected with `KS3201`. Nested assignment such as `a.b.c = 1` remains outside v0.10.

## Option runtime contract

`List<T>.get(Int)` now has one contract in Typed HIR, the interpreter, and generated native binaries:

- valid index: `Some(value)`
- invalid index: `None()`

Generic functions returning `Option<T>` therefore preserve their declared runtime contract instead of failing with `KS3106`.

## Ceremony measurement

Run:

```bash
./bench/ceremony/check.sh
```

The first ten tasks are checked as Koschei programs and measured against equivalent Python and Go sources. v0.10 reports the `KS/Python` and `KS/Go` ratios without making the ratio a release-blocking threshold yet.
