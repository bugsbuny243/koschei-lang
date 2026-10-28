# Koschei Data language ABI v1

Koschei's first backend data surface is deliberately smaller than a host-language
JSON API. It exposes an opaque `Data` value and only two initial operations:

```ks
let value = parse_json(source) or return
let canonical = encode_json(value) or return
```

`parse_json(String)` returns `Data or Error`. `encode_json(Data)` returns
`String or Error`. Both calls must use Koschei's `or` handling model.

JSON object braces inside a Koschei string are escaped because `{...}` is the
language's interpolation syntax:

```ks
let value = parse_json("\{\"enabled\":true\}") or return
```

## Why Data is opaque

Decoded values are not exposed as Python dictionaries, Go maps, binary floats,
or arbitrary mutable objects. That prevents backend-specific value semantics
from becoming part of the language contract. In particular:

- JSON numbers retain exact canonical decimal text;
- duplicate object keys are rejected;
- object output order is deterministic;
- capabilities and host objects cannot be hidden inside serialized data;
- a `Data` value cannot be printed, interpolated, or passed to `Error` without
  first being explicitly encoded.

The accessors below and future schema validation operate on this same opaque
value rather than revealing the bootstrap representation.

## Reading Data

| Method | Result |
|---|---|
| `kind()` | `String`: `object`, `array`, `string`, `number`, `bool` or `null` |
| `get(key)` | `Data or Error`: an object's member |
| `at(index)` | `Data or Error`: an array's item, counted from 0 |
| `length()` | `Int or Error`: an array's items or an object's members |
| `keys()` | `List<String> or Error`: an object's keys, in code point order (the order `encode_json` writes) |
| `text()` | `String or Error`: a string |
| `number()` | `String or Error`: a number's canonical text, for `decimal()` or display |
| `int()` | `Int or Error`: an integer number in the signed 64-bit range |
| `bool()` | `Bool or Error` |
| `is_null()` | `Bool` |

A method called on the wrong kind, a missing key or index, and a number that
is not an Int (`2.5`, `1e30`) are `KS3709` Error values naming what was
expected and what was found:

```text
KS3709: JSON değeri string değil: null
KS3709: JSON nesnesinde "total" anahtarı yok
KS3709: JSON dizisinde 2 indeksi yok (uzunluk 2)
KS3709: JSON sayısı Int değil: 2.5
```

Two `Data` values are equal when their JSON values are: objects by members,
arrays in order, numbers by canonical text.

## Writing JSON text

`json_quote(text)` returns the JSON string literal for a String: quotes and
the escapes `encode_json` writes (`\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`,
`\u00XX` for other control characters). A program builds a JSON reply from
quoted strings and numbers without escaping by hand:

```ks
let name = json_quote(customer) or return
let reply = "\{\"customer\": {name}, \"lines\": {count}\}"
```

Its result obeys the 16 MiB String budget (`KS3502`).

## Enforced budgets

The default v1 operation enforces all advertised security dimensions in both the
Python bootstrap and generated native Go runtime:

| Operation | Enforced limits |
|---|---|
| `parse_json` | input bytes, value nodes, tree depth |
| `encode_json` | output bytes, value nodes, tree depth |

Current defaults are 1 MiB input, 1 MiB output, 100,000 nodes, and depth 64.
Limits are checked while constructing or writing the value. Koschei does not
first create an unbounded host object and inspect it afterwards.

## Errors

The public ABI returns explicit KS370x error values in every executor and in
native binaries; the shared codec core numbers them KS360x internally, and
KS3601 and KS3602 remain reserved for execution step and call-depth budgets.

- `KS3701` input byte limit
- `KS3702` depth limit
- `KS3703` node limit
- `KS3704` duplicate object key
- `KS3705` malformed JSON or invalid Unicode
- `KS3707` output byte limit
- `KS3708` invalid Data encoding boundary
- `KS3709` a read of the wrong kind, a missing key or index, or a number that
  is not an Int

These are ordinary fallible values and use the same `or return`, `or value`, or
`or { ... }` handling model as the rest of Koschei.

## Interpreter/native parity

Both execution paths consume the `koschei.data-json/v1` contract. Binaries
built by `ks build` (MIR-Go) embed the audited native Go core
(`native/datajson`) only when the program uses JSON, and import no third-party
JSON library. The Python and Go cores give the same bytes for the same input,
error messages and byte offsets included; `tests/test_data_access_v1.py`
compares the methods, `json_quote` and the failures under the checked-AST
interpreter, the canonical MIR executor, `ks run` and the binary.

Run the example with:

```bash
ks check examples/data_v1.ks
ks run examples/data_v1.ks
ks build examples/data_v1.ks -o data-v1
./data-v1
```

Expected output:

```text
{"active":true,"balance":1,"roles":["owner"]}
```

## Deliberate boundary

V1 reads Data but does not yet construct or change it, and has no schema
validation; JSON output is built as text with `json_quote`. Those operations
will be added only with typed contracts, explicit resource bounds, and
interpreter/native parity. The opacity is a security property, not an
unfinished host-object cast.
