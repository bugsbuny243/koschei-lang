# V5 generic struct and enum contracts

Koschei now supports user-declared type parameters on structs and enums. The
compiler infers concrete arguments from constructor values and preserves them
through fields, function boundaries, `match`, modules, the interpreter, and the
native Go backend.

```ks
struct Box<T> {
    value: T,
}

enum Maybe<T> {
    Present(T),
    Missing,
}

fn boxed(value: Int) -> Box<Int> {
    return Box { value: value }
}

fn main() {
    let box = boxed(41)
    let item = Present("Ada")
    let name = match item {
        Present(value) => value,
        Missing => "none",
    }

    println(box.value + 1)
    println(name.trim())
}
```

The struct literal infers `Box<Int>`. `Present("Ada")` infers
`Maybe<String>`, so the `Present(value)` match binding is `String`. Call sites do
not repeat `<Int>` or `<String>` when the values already provide enough evidence.

## Contracts and ambiguity

Public type positions use explicit arguments:

```ks
struct Pair<T, U> {
    left: T,
    right: U,
}

fn left_number(pair: Pair<Int, String>) -> Int {
    return pair.left
}
```

Raw `Pair` is rejected because it would erase the API contract. Conflicting or
missing inference is `KS1307`; Koschei does not silently fall back to a dynamic
value. A payloadless generic enum variant may carry unknown arguments until an
expected contract supplies them, so `Missing()` can be returned from a function
whose result is `Maybe<Int>`.

`Map<K, V>` may appear inside a generic declaration, but every concrete Map key
still has to become `String`. For example, `Cache { entries: {"port": 8080} }`
infers `Cache<String, Int>`.

## Authority cannot hide behind a type parameter

<!-- verify: expect KS2402 -->
```ks
struct Box<T> {
    value: T,
}

fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://example.com")
    let hidden = Box { value: net }
}
```

The compiler rejects this with `KS2402`. The same rule applies to generic enum
payloads and explicit types such as `Box<NetCaps>`. Generic authority flow stays
closed until Koschei has an explicit effect-generic design; an unconstrained `T`
never becomes an authority-laundering escape hatch.

## Migration boundary

Typed HIR owns inference and substitution. The v0.9 semantic checker receives an
erased compatibility view only after the structural contract passes. The
interpreter retains inferred aggregate arguments for defensive runtime checks;
the native backend relies on the same pre-codegen Typed HIR gate. This bridge is
removed when backend-independent MIR becomes the single input to both runtimes.
