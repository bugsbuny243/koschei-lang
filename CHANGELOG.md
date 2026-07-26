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
- Add immutable structural type nodes for named, generic, union and unknown types.
- Add the first Typed HIR lowering pass with `List<T>` / `Map<String, V>` literal
  inference, `for` element propagation and `Option` / `Result` narrowing.
- Reject collection operations that are unsafe for any possible union member with
  `KS1306` before interpreter or native code generation.

The V5 design principle is: **security beyond ambient-authority languages and a
writing experience simpler than Python without hiding dangerous effects.**
