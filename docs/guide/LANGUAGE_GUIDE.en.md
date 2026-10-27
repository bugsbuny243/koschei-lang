# The Koschei Language Guide

This guide covers the language as it runs today. Every program in it is
executed by `tests/test_language_guide_v1.py`: a program followed by an
`output` block must print exactly that block under `ks run`, and must also
pass `ks check`. When the native backend admits a program, the compiled
binary must print the same bytes.

Turkish edition: [`LANGUAGE_GUIDE.tr.md`](LANGUAGE_GUIDE.tr.md).

## 1. Install and run

```sh
pip install .            # Python 3.12+; installs the `ks` command
ks run hello.ks          # check and run
ks build hello.ks -o hello && ./hello   # native binary (needs Go 1.24+)
```

```ks
fn main() {
    println("Hello, Koschei")
}
```

```output
Hello, Koschei
```

A program is checked completely before it runs. A type error, a missing
capability or an unhandled error never reaches execution.

## 2. Values

```ks
fn main() {
    let name = "Ada"
    let mut count: Int = 2
    count = count + 1
    println("{name} has {count} items")
    println(7 / 2)
    println(7 % 2)
    println(7.0 / 2.0)
    println(3 > 2 && !(1 == 2))
}
```

```output
Ada has 3 items
3
1
3.5
true
```

- `let` bindings are immutable; `let mut` states the intent to change one.
- Types are inferred; `let count: Int = 2` documents and enforces one.
- `Int` is signed 64-bit, `Float` is 64-bit, `String` is UTF-8, `Bool` is
  `true`/`false`. There is no `null`.
- `"{expression}"` interpolates any expression.

## 3. Lists and loops

```ks
fn total(prices: List<Int>) -> Int {
    let mut sum = 0
    for price in prices {
        if price < 0 {
            continue
        }
        sum = sum + price
    }
    return sum
}

fn main() {
    let prices = [120, -5, 30]
    println(total(prices))
    let more = prices.push(50)
    println("{prices.length()} -> {more.length()}")
    let first = prices.get(0) or 0
    println(first)
    let missing = prices.get(10) or -1
    println(missing)
    let mut i = 0
    while i < 10 {
        i = i + 3
        if i > 6 {
            break
        }
    }
    println(i)
}
```

```output
150
3 -> 4
120
-1
9
```

Lists are values: `push` returns a new list and leaves the original alone.
`get` may find nothing, so its result must be handled, here with `or`.

## 4. Errors are values

A function that can fail says so in its type, and the caller must handle the
failure. `or` gives three ways to do that: `or return ...` passes it up,
`or value` substitutes a default, `or { ... }` runs a block.

```ks
fn parse_port(text: String) -> Result<Int, Error> {
    let port = text.to_int() or return Err(Error("not a number: {text}"))
    if port < 1 || port > 65535 {
        return Err(Error("out of range: {port}"))
    }
    return Ok(port)
}

fn main() {
    let ok = parse_port("8080") or 0
    println(ok)
    let fallback = parse_port("http") or 80
    println(fallback)
    let message = match parse_port("70000") {
        Ok(port) => "port {port}",
        Err(error) => "refused: {error}",
    }
    println(message)
}
```

```output
8080
80
refused: out of range: 70000
```

Runtime failures are values too: Int overflow (`KS3501`), division by zero
and a value over the memory budget (`KS3502`) produce Error values at the
same point in every executor, and `or` catches them.

```ks
fn main() {
    let big = 9223372036854775807
    let overflow = big + 1 or -1
    println(overflow)
    let safe = 10 / 0 or 0
    println(safe)
}
```

```output
-1
0
```

## 5. Enums, `match` and structs

```ks
enum Shape {
    Circle(Int),
    Square(Int),
    Empty,
}

fn area(shape: Shape) -> Int {
    return match shape {
        Circle(r) => 3 * r * r,
        Square(side) => side * side,
        Empty => 0,
    }
}

struct Point {
    x: Int,
    y: Int,
}

fn main() {
    println(area(Circle(2)))
    println(area(Square(3)))
    println(area(Empty()))
    let p = Point { x: 1, y: 2 }
    let mut q = p
    q.x = 10
    println(p)
    println(q)
    println(p == Point { x: 1, y: 2 })
}
```

```output
12
9
0
Point { x: 1, y: 2 }
Point { x: 10, y: 2 }
true
```

`match` must cover every variant. Structs have value semantics: assigning a
field through `q` builds a new value and never changes `p`.

## 6. Generics and maps

```ks
fn first_or<T>(items: List<T>, fallback: T) -> T {
    let item = items.get(0) or return fallback
    return item
}

fn main() {
    println(first_or([3, 4], 0))
    println(first_or(["a"], "none"))
    let ages = {"ada": 36, "alan": 41}
    let age = ages.get("ada") or 0
    println(age)
    let older = ages.set("grace", 85)
    println(older.keys())
    println(ages.contains("nobody"))
}
```

```output
3
a
36
["ada", "alan", "grace"]
false
```

Map keys are Strings and keep insertion order. `get` on a missing key is an
Error value, so handle it with `or` or ask `contains` first.

### Bytes

`String` is always UTF-8 text; binary data is `Bytes`, and the two never
convert silently. Sources: `input.read_bytes()`, `disk.read_bytes(path)`,
`random.bytes(n)`; see [`../BYTES_V1.md`](../BYTES_V1.md).

```ks
fn main() {
    let data = "héllo".to_bytes()
    println(data)
    println(data.length())
    let head = data.slice(0, 2) or data
    println(head.to_text())
    let key = bytes_from_hex("00ff") or data
    println(key + head)
}
```

```output
Bytes(68c3a96c6c6f)
6
KS3430: Bytes geçerli UTF-8 metin değil.
Bytes(00ff68c3)
```

## 7. Modules and the Core Library

`import name` binds a sibling file `name.ks` or a Core Library module. The
Core Library is written in Koschei and compiled with your program; the full
list is in [`../reference/CORE_LIBRARY.md`](../reference/CORE_LIBRARY.md).

```ks
import text
import list
import secure

fn main() {
    println(text.starts_with("koschei.ks", "koschei"))
    println(text.replace("a-b-c", "-", "+") or "")
    println(text.lines("one\ntwo"))
    println(list.reverse([1, 2, 3]))
    println(list.first(["x", "y"]))
    println(secure.hash("koschei") or "?")
}
```

```output
true
a+b+c
Ok(["one", "two"])
[3, 2, 1]
Some("x")
sha3-256:3997da0d8a19346db3fb4c5be74689b753e506c8a03f2bba28be7b3bd3125e8c
```

`secure` digests come from the host's audited SHA3-256; Koschei implements no
cryptographic primitive of its own.

## 8. Pure functions

`pure fn` promises no effect: no output, no capability, no call to anything
that has one. The checker proves it (`KS3940`).

```ks
pure fn double(value: Int) -> Int {
    return value * 2
}

fn main() {
    println(double(21))
}
```

```output
42
```

## 9. Capabilities

Koschei has no ambient authority. `main` may take one `SystemCaps`, and every
effect beyond printing goes through a token narrowed from it. A function
without a token cannot reach the disk, the network, the environment, the
program's input, the clock or randomness, and the checker proves it.

```ks
fn greet(input: InputCaps) -> String or Error {
    let args = input.args() or return Error("no arguments")
    let name = args.get(0) or return Error("usage: greet NAME")
    return "Hello, {name}!"
}

fn main(caps: SystemCaps) {
    let message = greet(caps.input.allow(1024)) or "usage: greet NAME"
    println(message)
}
```

```output
usage: greet NAME
```

`ks run greet.ks Ada` prints `Hello, Ada!`. The rules:

| Root | Narrowed by | Gives |
|---|---|---|
| `caps.input` | `allow(max_stdin_bytes)` | `args()`, `read_text()` |
| `caps.clock` | `allow(resolution_ms)` | `now_ms()`, `monotonic_ms()` |
| `caps.random` | `allow(max_bytes)` | `hex(count)`, `below(bound)` |
| `caps.disk` | `allow(prefix)`, `allow_read_only(prefix)` | `read`, `write`, `list`, `delete` |
| `caps.env` | `allow(name)` | `get()` |
| `caps.net` | `allow(origin)` | `get(url)` |

- A root cannot act directly (`KS2402`); a narrowed token cannot widen
  (`KS2403`) or do what it was not given (`KS2404`).
- Tokens move: passing one to a function hands it over (`KS3931` on reuse).
- Tokens cannot be stored in lists or maps (`KS2401`), compared (`KS2407`) or
  printed meaningfully (they print as `<InputCaps>`).
- `ks caps app.ks` prints every grant with its scope: the program cannot
  reach anything outside that list.

```ks
fn main(caps: SystemCaps) {
    let clock = caps.clock.allow(1000)
    let now = clock.now_ms()
    println(now % 1000 == 0)
    let random = caps.random.allow(8)
    let token = random.hex(8) or ""
    println(token.length())
    println(random.hex(8))
    println(random.below(6))
}
```

```output
true
16
KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla 8 bayt üretebilir.
KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla 8 bayt üretebilir.
```

The token may produce 8 bytes in all: the first `hex(8)` spends them, so the
second `hex(8)` and `below` (8 bytes) get the `KS3450` Error value and draw
nothing. Runtime messages are
Turkish today; their codes are stable.

## 10. Tools

| Command | Does |
|---|---|
| `ks check app.ks` | full check, no execution |
| `ks run app.ks [ARG ...]` | check, then run on sealed MIR under step and call-depth budgets |
| `ks build app.ks -o app` | native binary through MIR-Go |
| `ks caps app.ks` | authority manifest |
| `ks fmt app.ks` | canonical formatting |
| `ks explain KS2402` | explanation of a diagnostic (`--lang en` / `--lang tr`) |
| `ks lock` / `ks build --locked` | module lock and verified builds |

Every diagnostic is listed in [`../reference/ERROR_CODES.md`](../reference/ERROR_CODES.md).

## 11. Native builds

`ks build` compiles programs that use the core language, structs, enums,
generics, modules, the Core Library, program input, the clock and randomness,
and on linux/amd64 the disk (read, write, delete), the environment, the
network and the loopback server through a confined broker ([`../NATIVE_BROKER_V1.md`](../NATIVE_BROKER_V1.md),
[`../NET_V1.md`](../NET_V1.md)). The binary prints
the same bytes and the same Error values as `ks run`. Maps, callback members
(`filter`, `map`, `sort`) and processes are refused with
`KS4004` instead of compiled differently; see [`../MIR_GO_CONFORMANCE_ADAPTER_V2.md`](../MIR_GO_CONFORMANCE_ADAPTER_V2.md).

## 12. Limits worth knowing

- A String holds at most 16 MiB of UTF-8 and a List at most 1,048,576 items
  (`KS3502`).
- `ks run` stops a program after 1,000,000 steps by default (`--max-steps`)
  and at 512 nested calls.
- There is no interactive line reading yet, and the broker exists on
  linux/amd64 only ([`../SERVE_KNOWHERE_V1.md`](../SERVE_KNOWHERE_V1.md)); see `KOSCHEI_SATISA_HAZIRLIK_V1.md` for the plan.
