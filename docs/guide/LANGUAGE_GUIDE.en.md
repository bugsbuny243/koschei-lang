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

### Everyday syntax in one program

```ks
enum Light {
    Red,
    Green,
}

fn size(n: Int) -> String {
    if n > 100 {
        return "large"
    } else if n > 10 {
        return "medium"
    } else {
        return "small"
    }
}

fn positive(value: Int) -> Bool {
    return value > 0
}

fn double(value: Int) -> Int {
    return value * 2
}

fn main() {
    println(size(42))
    let words = "pear, fig ,apple".split(",") or []
    let mut clean: List<String> = []
    for word in words {
        clean = clean.push(word.trim())
    }
    let sorted = clean.sort() or []
    println(" | ".join(sorted))
    let numbers = [5, -2, 8]
    println(numbers.filter(positive) or [])
    println(numbers.map(double) or [])
    let mut counts: Map<String, Int> = {}
    for word in ["a", "b", "a"] {
        let seen = counts.get(word) or 0
        counts = counts.set(word, seen + 1)
    }
    println(counts)
    println("12".to_int() or 0)
    print("no newline, ")
    println("then one")
    match Green() {
        Red => println("stop"),
        Green => println("go"),
    }
}
```

```output
medium
apple | fig | pear
[5, 8]
[10, -4, 16]
{"a": 2, "b": 1}
12
no newline, then one
go
```

- `if` takes `else if` and `else`. Conditions must be `Bool`.
- There is no range loop. Count with `while`, or iterate a list with `for`.
- An empty list or map needs its type: `let mut xs: List<Int> = []`,
  `let mut m: Map<String, Int> = {}`.
- String methods: `length()`, `contains(text)`, `trim()`, `split(separator)`,
  `join(list)`, `to_int()`, `to_float()`. `split`, `to_int` and `to_float`
  can fail, so handle them with `or`.
- List methods: `length()`, `get(index)`, `push(item)`, `contains(item)`,
  `sort()`, `filter(function)`, `map(function)`. `filter` and `map` take a
  function name or a lambda (below). `sort`, `filter` and `map` can fail,
  so handle them with `or`.
- `print` writes without a newline; `println` adds one.
- `match` works as a statement as well as an expression. A variant without a
  payload is built with parentheses (`Green()`) and matched without (`Green`).

### Lambdas

`fn(parameters) -> Type { ... }` written where a value is expected is a
lambda: a function without a name. It goes wherever a function name can go,
such as `filter`, `map`, `any`, `partition` and `scan`, or into a variable.

```ks
fn main() {
    let numbers = [5, -2, 8, 0]
    println(numbers.filter(fn(x: Int) -> Bool { return x > 0 }) or [])
    println(numbers.map(fn(x: Int) -> Int { return x * x }) or [])
    let shout = fn(word: String) -> String { return "{word}!" }
    println(shout("tea"))
}
```

```output
[5, 8]
[25, 4, 64, 0]
tea!
```

A lambda does not capture: its body sees its own parameters, other functions
and imported modules, never a variable of the function it is written in
(`KS1103`). Pass such a value as a parameter, or write a named function. So
a lambda can never quietly hold a capability token.

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

A bare `or return` hands the failure itself to the caller, so the function
must be able to return it: `-> T or Error` when the failure is an Error, an
`Option` or `Result` return type when it is `None` or `Err`. A function
without a return type cannot (`KS1304`).
Only `main` may return an Error it does not declare: the program ends with
`KOSCHEI RUNTIME ERROR: <message>` and exit status 1.

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

### JSON

`parse_json` turns text into an opaque `Data` value; the `json_` functions
read it. Braces inside a Koschei string are escaped (`\{`, `\}`) because
`{...}` is interpolation.

```ks
fn price(item: Data) -> Int or Error {
    let field = json_get(item, "price") or return Error("item has no price")
    let value = json_int(field) or return Error("price is not a whole number")
    return value
}

fn main() {
    let text = "\{\"shop\":\"Ada's\",\"open\":true,\"items\":[\{\"name\":\"pen\",\"price\":3\},\{\"name\":\"ink\",\"price\":12\},\{\"name\":\"gift\"\}]\}"
    let order = parse_json(text) or return Error("not JSON")
    let shop = json_get(order, "shop") or return Error("no shop")
    println(json_text(shop) or "?")
    println(json_kind(order))
    println(json_keys(order) or [])
    println(json_has(order, "discount"))
    let list = json_get(order, "items") or return Error("no items")
    println(json_length(list) or 0)
    let mut total = 0
    for item in json_items(list) or [] {
        let name = json_get(item, "name") or item
        let cost = price(item) or 0
        println("{json_text(name) or "?"}: {cost}")
        total = total + cost
    }
    println(total)
    let first = json_at(list, 0) or return Error("empty")
    println(encode_json(first) or "?")
    println(json_at(list, 9))
    println(json_int(shop))
}
```

```output
Ada's
object
["shop", "open", "items"]
false
3
pen: 3
ink: 12
gift: 0
15
{"name":"pen","price":3}
KS3710: json_at(): index 9 is outside 0..2
KS3709: json_int() expects a JSON number, found string
```

| Function | Returns | For |
|---|---|---|
| `parse_json(text)` | `Data or Error` | text to `Data` |
| `encode_json(data)` | `String or Error` | `Data` back to canonical JSON text |
| `json_kind(data)` | `String` | `"object"`, `"array"`, `"string"`, `"number"`, `"bool"` or `"null"` |
| `json_has(data, key)` | `Bool` | whether an object has the member |
| `json_get(data, key)` | `Data or Error` | an object member |
| `json_at(data, index)` | `Data or Error` | an array element |
| `json_text(data)` | `String or Error` | a JSON string |
| `json_int(data)` | `Int or Error` | a whole number within `Int` |
| `json_float(data)` | `Float or Error` | any number |
| `json_bool(data)` | `Bool or Error` | `true` or `false` |
| `json_length(data)` | `Int or Error` | elements of an array, members of an object |
| `json_keys(data)` | `List<String> or Error` | member names, in document order |
| `json_items(data)` | `List<Data> or Error` | array elements, to use with `for` |

- Nothing is converted silently: `json_int` refuses `2.5` and a string, and
  the wrong kind is a `KS3709` Error value. A missing member or index is
  `KS3710`. Handle both with `or`.
- A `Data` value cannot be printed or interpolated; call `encode_json` or
  read a field first.
- All of these are pure: they need no capability and work inside `pure fn`.
- JSON runs under `ks run`. `ks build` refuses programs that use `Data`
  (`KS4004`) until the native backend supports it.

To write JSON, build the text with the `json` Core Library module; its parts nest:

```ks
import json

fn main() {
    let tags = json.array([json.string("pen"), json.string("ink")])
    let order = json.object({"shop": json.string("Ada's"), "total": json.int(15), "tags": tags})
    println(order)
    let data = parse_json(order) or return Error("not JSON")
    println(json_kind(data))
}
```

```output
{"shop":"Ada's","total":15,"tags":["pen","ink"]}
object
```

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
import math
import secure
import time

fn main() {
    println(text.starts_with("koschei.ks", "koschei"))
    println(text.replace("a-b-c", "-", "+") or "")
    println(text.lines("one\ntwo"))
    println(list.reverse([1, 2, 3]))
    println(list.first(["x", "y"]))
    println(math.max(3, 8))
    println(math.pow(2, 10) or 0)
    println(math.pow(2, 63))
    println(time.iso_utc(1762933548000) or "?")
    println(secure.hash("koschei") or "?")
}
```

```output
true
a+b+c
Ok(["one", "two"])
[3, 2, 1]
Some("x")
8
1024
math.pow: the result is outside Int
2025-11-12T07:45:48Z
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
| `caps.net` | `allow(origin)` | `get(url)`, `post(url, content_type, body)` |
| `caps.db` | `allow(path, max_rows, max_bytes, deadline_ms)` | `exec(sql, params)`, `query(sql, params)` |

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

### Reading a file

```ks
fn load(disk: DiskReadCaps, path: String) -> String or Error {
    let content = disk.read(path) or return Error("cannot read {path}")
    return content
}

fn main(caps: SystemCaps) {
    let data = caps.disk.allow_read_only("/data")
    let content = load(data, "/data/input.txt") or "missing"
    println(content)
}
```

`read(path)` returns the file's text or an Error value, so the caller decides
what a missing file means. Here the program prints `missing` when
`/data/input.txt` cannot be read. `ks caps` reports exactly one grant for it:
disk, `/data`, read-only. `list(path)` returns the names in a directory, and a
token from `allow(prefix)` can also `write(path, text)` and `delete(path)`.

### Serving HTTP

The `http` Core Library module reads what a server receives: `route` matches
a request target against a pattern and captures the `:name` segments,
decoded; `query` reads the query string; `params` reads a form body;
`escape_html` makes text safe to put in a page. They are pure, so the
answer to a request can be computed and tested without a socket.

```ks
import http

fn page(target: String) -> String {
    let found = http.route("/users/:name", target) or return "404"
    let name = found.get("name") or "?"
    let query = http.query(target) or return "400 bad query"
    let tab = query.get("tab") or "posts"
    return "user {name}, tab {tab}"
}

fn main() {
    println(page("/users/ada%20lovelace?tab=likes"))
    println(page("/users/alan"))
    println(page("/teams/1"))
    println(http.escape_html("<b>Tom & Jerry</b>"))
}
```

```output
user ada lovelace, tab likes
user alan, tab posts
404
&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;
```

A server takes `caps.serve.allow(bind, max_requests, max_request_bytes,
max_response_bytes, deadline_ms)`. `accept()` waits for one request and
`reply_as(status, content_type, body)` answers it. The token moves into
the function that serves, so the loop lives there, and a pure function
decides each reply.

```ks
import http
import json

struct Reply {
    status: Int,
    content_type: String,
    body: String,
}

// Pure: decides the answer from the request target alone.
fn respond(target: String) -> Reply {
    let found = http.route("/users/:name", target) or {
        return Reply { status: 404, content_type: "text/plain", body: "not found" }
    }
    let name = found.get("name") or "?"
    let body = json.object({"name": json.string(name)})
    return Reply { status: 200, content_type: "application/json", body: body }
}

fn serve(server: ServeCaps, rounds: Int) -> Int {
    let mut served = 0
    while served < rounds {
        served = served + 1
        let request = server.accept() or {
            continue
        }
        let reply = respond(request.path())
        let sent = server.reply_as(reply.status, reply.content_type, reply.body) or {
            continue
        }
    }
    return served
}

fn main(caps: SystemCaps) {
    let server = caps.serve.allow("127.0.0.1:8080", 1000, 65536, 65536, 5000)
    println(serve(server, 1000))
}
```

`curl localhost:8080/users/ada` answers `{"name":"ada"}`; any other path
gets `404`. `ks caps` reports one grant: serve, `127.0.0.1:8080` with its
four budgets. `0.0.0.0:8080` would listen on every interface, for a
public server. The server runs the same under `ks build`. See [`../SERVE_KNOWHERE_V1.md`](../SERVE_KNOWHERE_V1.md) for every
rule.

### A database

`caps.db.allow(path, max_rows, max_bytes, deadline_ms)` opens one SQLite
file: an absolute path, the most rows a query may return, the largest the
file may grow and how long one statement may run. `exec(sql, params)` returns
the number of rows changed; `query(sql, params)` returns the rows as `Data`,
a JSON array of objects read with the `json_` functions.

The SQL must be a string literal. Values never go into the text: they bind
to `?` placeholders from a JSON array built with the `json` module. A
statement assembled at run time is `KS2462` at check time, so SQL injection
cannot be written.

```ks
import json

fn add_note(db: DbCaps, body: String) -> Int or Error {
    let made = db.exec("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)", "[]") or return Error("cannot create the table")
    let added = db.exec("INSERT INTO notes (body) VALUES (?)", json.array([json.string(body)])) or return Error("cannot save the note")
    let rows = db.query("SELECT count(*) AS total FROM notes", "[]") or return Error("cannot count")
    let row = json_at(rows, 0) or return Error("no row")
    let total = json_get(row, "total") or return Error("no total")
    let count = json_int(total) or return Error("not a number")
    return count
}

fn main(caps: SystemCaps) {
    let db = caps.db.allow("/tmp/notes.db", 1000, 10485760, 2000)
    let count = add_note(db, "buy tea") or 0
    println("{count} notes")
}
```

Each run adds a row: the first prints `1 notes`, the next `2 notes`. A
statement may read and write tables, indexes, views and triggers; `ATTACH`,
`PRAGMA` and extensions are refused (`KS3484`), so the program reaches this
one file only. The database works under `ks run`; `ks build` refuses it for
now (`KS4004`). See [`../DB_V1.md`](../DB_V1.md).

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
generics, maps, modules, the Core Library, program input, the clock and randomness,
and on linux/amd64 the disk (read, write, delete), the environment, the
network and the loopback server through a confined broker ([`../NATIVE_BROKER_V1.md`](../NATIVE_BROKER_V1.md),
[`../NET_V1.md`](../NET_V1.md)). The binary prints
the same bytes and the same Error values as `ks run`. Callback members
(`filter`, `map`, `sort`) and processes are refused with
`KS4004` instead of compiled differently; see [`../MIR_GO_CONFORMANCE_ADAPTER_V2.md`](../MIR_GO_CONFORMANCE_ADAPTER_V2.md).

## 12. Limits worth knowing

- A String holds at most 16 MiB of UTF-8 and a List at most 1,048,576 items
  (`KS3502`).
- `ks run` stops a program after 1,000,000 steps by default (`--max-steps`)
  and at 512 nested calls.
- There is no interactive line reading yet, and the broker exists on
  linux/amd64 only ([`../SERVE_KNOWHERE_V1.md`](../SERVE_KNOWHERE_V1.md)).
