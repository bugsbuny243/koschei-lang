# Changelog

## Unreleased — V5 foundation

- Reject duplicate top-level declarations before interpreter/native backends.
- Require every path of a value-returning function to return.
- Reject values returned from ordinary `Void` functions.
- Detect statements unreachable after unconditional return flow.
- Add an explicit binary-entrypoint contract (`KS1801`).
- Add a zero-dependency LSP with diagnostics, formatting, hover, definitions,
  symbols and completion.
- Upgrade the official VS Code extension from save-time checks to live LSP.

The V5 design principle is: **security beyond ambient-authority languages and a
writing experience simpler than Python without hiding dangerous effects.**
