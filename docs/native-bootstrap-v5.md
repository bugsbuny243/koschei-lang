# V5 native bootstrap: first Python-exit slice

Koschei's public compiler is still bootstrapped in Python. This directory starts
removing that implementation dependency without weakening the language contract
or pretending that a rewrite is complete.

The first native slice is a deterministic Koschei lexer in `native/lexer` and a
small inspection executable in `native/cmd/ksc-native`. It recognizes the current
core token vocabulary, Unicode identifiers, comments, exact number text, escaped
strings, and balanced expression interpolation.

```bash
cd native
go test ./...
go run ./cmd/ksc-native ../examples/showcase.ks
```

## Security properties of this slice

- No third-party dependencies.
- No regular-expression engine or dynamic code execution.
- Invalid UTF-8 fails closed.
- Source bytes and emitted tokens have explicit budgets.
- Numeric text is preserved exactly, so a hostile huge integer cannot overflow
  the lexer host before semantic range checking.
- Columns are counted as Unicode characters rather than UTF-8 bytes.
- Interpolation scanning tracks nested braces and quoted strings deterministically.
- Fuzz seeds exercise malformed input and the lexer API is required not to panic.

## Honest boundary

This is not yet the default compiler and it does not make a claim of immunity to
all attacks. The Python frontend remains the compatibility oracle while native
lexer parity expands. Parser, typed HIR, sealed MIR verification, code generation,
and the capability runtime still need independent native implementations before
Python can be removed from installation.

## Exit sequence

1. Differential-token tests compare Python and native token streams on the full
   corpus and generated adversarial sources.
2. A native parser consumes only the stable token contract.
3. Typed HIR and sealed MIR validation move behind a language-neutral schema.
4. One native backend executes normalized MIR directly, without AST fallback.
5. The compiler is rebuilt by the previous trusted compiler and reproducible
   outputs are compared before the Python bootstrap is retired.

The end state is a self-hosting Koschei compiler with a small, reviewable native
bootstrap and an explicit capability ABI. The security target is measurable:
less ambient authority, smaller trusted code, bounded resource use, reproducible
builds, and fail-closed behavior when a guarantee cannot be provided.
