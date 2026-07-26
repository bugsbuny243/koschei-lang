# Changelog

## Unreleased — V5 foundation

- Reject duplicate top-level declarations before interpreter/native backends.
- Require every path of a value-returning function to return.
- Reject values returned from ordinary `Void` functions.
- Detect statements unreachable after unconditional return flow.
- Add an explicit binary-entrypoint contract (`KS1801`).
- Add a zero-dependency LSP with diagnostics, formatting, hover, definitions,
  symbols and completion.
- Expose the language server through `ks lsp` and `python -m koschei lsp` while
  retaining `ks-lsp` as a compatibility alias.
- Upgrade the official VS Code extension from save-time checks to live LSP.
- Add immutable structural type nodes for named, generic, union and unknown types.
- Add the first Typed HIR lowering pass with `List<T>` / `Map<String, V>` literal
  inference, `for` element propagation and `Option` / `Result` narrowing.
- Reject collection operations that are unsafe for any possible union member with
  `KS1306` before interpreter or native code generation.
- Expose `List<T>` and `Map<String, V>` as source-level contracts in parameters,
  returns, struct fields, enum payloads and module APIs.
- Enforce typed collection arguments and return values in Typed HIR while keeping
  raw v0.9 `List` / `Map` annotations as compatibility wildcards.
- Prevent capabilities from being hidden inside typed collections, `Option`,
  `Result`, structs or enum payloads.
- Keep live LSP diagnostics, interpreter checks and native builds on the same
  typed-collection contract.
- Make the defensive interpreter runtime recursively enforce `List<T>` and
  `Map<String, V>` contracts, including nested collections.
- Separate ordinary runtime type-contract mismatches (`KS3106`) from genuine
  capability type-integrity violations (`KS3401`).
- Define `Int / Int` as checked integer division truncated toward zero and keep
  interpreter/native behavior identical; `Float / Float` remains floating-point.
- Add declared generic functions such as `fn identity<T>(value: T) -> T`, with
  call-site inference, nested substitution and cross-module contracts.
- Keep generic inference identical across CLI checks, live LSP diagnostics,
  interpreter runtime checks and native Go builds; ambiguous inference fails with
  bilingual `KS1307` instead of falling back to a dynamic type.
- Keep capability-bearing generic substitutions closed until effect generics are
  explicit, preventing authority from being hidden behind an unconstrained `T`.

The V5 design principle is: **security beyond ambient-authority languages and a
writing experience simpler than Python without hiding dangerous effects.**
