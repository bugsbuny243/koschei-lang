# V5 native parser and syntax schema v1

`native/parser` is the second Python-exit slice. It consumes only the stable
`native/lexer` token contract and emits a deterministic JSON tree defined in
`native/syntax`.

```bash
cd native
go test ./...
go run ./cmd/ksc-native --ast ../examples/showcase.ks
```

The root object is explicitly versioned:

```json
{
  "schema": "koschei.syntax/v1",
  "kind": "Program",
  "imports": [],
  "structs": [],
  "enums": [],
  "functions": []
}
```

## Implemented grammar slice

The parser covers imports, generic structs, generic enums, generic functions,
parameters, structured generic and union type references, blocks, `let`, `return`,
`if/else`, `while`, `for`, assignment, `or` handlers, boolean and arithmetic
precedence, calls, members, exact literals, interpolated strings, list/map/struct
literals, and `match` expressions.

The syntax schema does not serialize numbers through a host integer or float.
A literal such as `1.0000000000000001` remains exact source text. Empty strings
also carry an explicit empty text value rather than becoming indistinguishable
from a missing field.

## Fail-closed resource model

The lexer already bounds source bytes and emitted tokens. AST mode adds independent
budgets for:

- emitted syntax nodes;
- syntax nesting depth;
- total bytes re-lexed inside interpolation expressions;
- total tokens emitted inside interpolation expressions.

All budget failures are located parser errors. Comment tokens, early EOF tokens,
missing terminal EOF, unknown interpolation segment kinds, and malformed syntax are
rejected rather than repaired or guessed.

## Compatibility gate

`tests/test_native_parser_v5.py` builds `ksc-native`, checks the versioned schema,
exact literals, deterministic output, and fail-closed budgets. It also compares
native parser acceptance with the Python bootstrap parser for every checked-in
`.ks` source. Acceptance parity is the first parser gate; full field-by-field AST
parity remains the next migration gate.

## Honest boundary

This parser does not type-check, lower to HIR/MIR, execute programs, load modules,
or grant capabilities. The Python compiler is still authoritative for semantic
analysis and code generation. `koschei.syntax/v1` is intentionally versioned so a
future incompatible tree change cannot silently reinterpret existing tooling.
