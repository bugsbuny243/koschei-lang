# Koschei data-json/v1

`koschei.data-json/v1` is the first bounded data codec shared by the Python
bootstrap and the native Go implementation. It is a security contract, not a
wrapper around either host language's JSON library.

## Value model

A value is one of:

- `null`
- `Bool`
- Unicode `String`
- exact decimal `Number`
- ordered JSON array
- String-keyed JSON object

Decoded numbers never pass through binary floating point. The codec stores a
canonical exact decimal text. Equivalent spellings such as `1.00`, `1e0`, and
`1` therefore encode as `1`; negative zero encodes as `0`. Scientific notation
is used only outside the inclusive plain-decimal exponent range `-6..20`.

Object keys are encoded in ascending Unicode scalar order. Strings use UTF-8,
short JSON escapes for common control characters, lowercase `\u00xx` for other
controls, and preserve ordinary Unicode characters. Lone surrogate escapes and
invalid UTF-8 are rejected.

## Mandatory budgets

Each decode and encode receives four positive limits:

- input bytes
- output bytes
- value nodes
- tree depth

The input-byte limit is checked before parsing. Node and depth limits are checked
while constructing or encoding the value. Output is accumulated only behind the
output-byte gate; callers never receive a partial successful JSON document.

## Errors

| Code | Meaning |
|---|---|
| `KS3601` | input byte limit exceeded |
| `KS3602` | depth limit exceeded |
| `KS3603` | node limit exceeded |
| `KS3604` | duplicate object key |
| `KS3605` | malformed JSON or invalid exact number |
| `KS3607` | output byte limit exceeded |
| `KS3608` | value is not encodable by data/v1 |

Offsets are UTF-8 byte offsets in both bootstraps.

## Security boundary

Host integers, host floating-point values, arbitrary objects, capabilities, and
future secret values are not silently serialized. Language integration must
convert approved Koschei values into the explicit data/v1 value model and keep
capability/secret rejection at that boundary.

The shared fixture `spec/data-json-v1-cases.json` is consumed by both Python and
Go tests. Public `data.parse_json` / `data.encode_json` operations remain
`reserved` until semantic typing and runtime wiring use this core in both
execution paths.
