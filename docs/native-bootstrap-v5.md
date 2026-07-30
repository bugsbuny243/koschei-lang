# V5 native bootstrap: Python-exit slices

Koschei's public compiler is still bootstrapped in Python. The `native` directory
removes that implementation dependency in small, machine-checked slices without
weakening the language contract or pretending that the migration is complete.

The first slice is a deterministic lexer in `native/lexer`. The second slice is a
bounded recursive-descent parser in `native/parser` that emits the versioned,
language-neutral `koschei.syntax/v1` tree from `native/syntax`.

```bash
cd native
go test ./...
go run ./cmd/ksc-native ../examples/showcase.ks
go run ./cmd/ksc-native --ast ../examples/showcase.ks
```

## Security properties

- No third-party Go dependencies.
- No regular-expression engine, dynamic code execution, or ambient authority.
- Invalid UTF-8 fails closed.
- Source bytes, emitted tokens, AST nodes, nesting depth, and interpolation work
  have explicit budgets.
- Numeric text is preserved exactly; hostile huge or precise numbers cannot
  overflow or silently round in the lexer/parser host.
- Empty token and AST string values remain explicit in JSON.
- Columns are counted as Unicode characters rather than UTF-8 bytes.
- Interpolation scanning tracks nested braces and quoted strings deterministically.
- Token and parser APIs have fuzz seeds and are required not to panic.
- Invalid token streams, comment leakage, and early EOF fail closed.

## Compatibility gates

`tests/test_native_lexer_parity_v5.py` treats the Python lexer as the temporary
compatibility oracle. It compares token kind, exact value, interpolation segments,
and Unicode locations over checked-in programs and deterministic adversarial input.

`tests/test_native_parser_v5.py` builds AST mode, validates `koschei.syntax/v1`,
checks exact literals and parser budgets, and requires native/Python parser
acceptance to agree for every checked-in `.ks` source. Full structural AST parity
is deliberately a separate next gate.

## Honest boundary

This is not yet the default compiler and it does not claim immunity to all attacks.
The Python frontend remains authoritative for semantic analysis while typed HIR,
sealed MIR verification, code generation, the capability runtime, and reproducible
self-hosting are moved behind native, versioned contracts.

## Exit sequence

1. **Complete:** native lexer with full differential token parity.
2. **First slice complete:** bounded native parser emitting `koschei.syntax/v1`,
   with full checked-in corpus acceptance parity.
3. Full field-by-field Python/native AST differential parity.
4. Typed HIR and sealed MIR validation behind language-neutral schemas.
5. One native backend executes normalized MIR directly, without AST fallback.
6. The compiler is rebuilt by the previous trusted compiler and reproducible
   outputs are compared before the Python bootstrap is retired.

The end state is a self-hosting Koschei compiler with a small, reviewable native
bootstrap and explicit capability ABI. The target remains measurable: less ambient
authority, smaller trusted code, bounded resource use, reproducible builds, and
fail-closed behavior when a guarantee cannot be provided.
