# Koschei Data language ABI v1

Koschei's first backend data surface is deliberately smaller than a host-language
JSON API. It exposes an opaque `Data` value and only two initial operations:

```ks
let value = parse_json(source) or return
let canonical = encode_json(value) or return
```

`parse_json(String)` returns `Data or Error`. `encode_json(Data)` returns
`String or Error`. Both calls must use Koschei's `or` handling model.

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

Future typed accessors and schema validation will operate on this same opaque
value rather than revealing the bootstrap representation.

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

The ABI returns explicit KS360x error values:

- `KS3601` input byte limit
- `KS3602` depth limit
- `KS3603` node limit
- `KS3604` duplicate object key
- `KS3605` malformed JSON or invalid Unicode
- `KS3607` output byte limit
- `KS3608` invalid Data encoding boundary

These are ordinary fallible values and use the same `or return`, `or value`, or
`or { ... }` handling model as the rest of Koschei.

## Interpreter/native parity

Both execution paths consume the `koschei.data-json/v1` contract. Generated
binaries embed the audited native Go core and do not import a third-party JSON
library. Shared fixtures and language-level tests require identical canonical
output and the same KS360x error class.

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

V1 does not yet expose field lookup, arrays, constructors, mutation, or schema
validation. Those operations will be added only with typed contracts, explicit
resource bounds, and interpreter/native parity. The opacity is a security
property, not an unfinished host-object cast.
