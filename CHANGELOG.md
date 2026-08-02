# Changelog

## 0.10.0 — Language ergonomics

- Add checked `Int % Int` with interpreter/native parity, truncation-toward-zero semantics, zero-divisor handling, and compile-time Float rejection.
- Add `break` and `continue` for `for` and `while`, `KS1901` outside loops, labelled Go lowering where required, and explicit MIR control-flow edges without changing ordinary-loop fallback contracts.
- Add optional local annotations such as `let value: Int = 5` while keeping inference as the default.
- Add block-bodied exhaustive `match` arms with tail-expression values and function-level `return` behavior.
- Allow direct struct field mutation only through `let mut` bindings; keep immutable bindings and nested field assignment closed with `KS3201`.
- Repair the `List<T>.get()` runtime ABI so valid indices return `Some(value)` and invalid indices return `None()` in both interpreter and native binaries, closing generic `Option<T>` return failures.
- Add stable localized parser diagnostic families `KS1001`–`KS1005` and loop/field diagnostics `KS1901` / `KS3201`.
- Add a ten-task `bench/ceremony/` corpus with equivalent Koschei, Python, and Go programs plus report-only CI measurement of `KS/Python` and `KS/Go` source-line ratios.
- Keep the release intentionally free of native-parser migration, Data ABI expansion, new budget infrastructure, lambdas, traits, `impl`, labelled loop control, concurrency, and region-memory work.

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
- Add user-defined generic structs and enums with constructor inference, field
  substitution, exhaustive-match payload typing, module contracts and native parity.
- Reject raw or ambiguous aggregate generics with `KS1307`; keep Map keys concretely
  String and prevent capability values from binding to aggregate type parameters.
- Preserve inferred aggregate arguments in the defensive interpreter runtime while
  the legacy semantic bridge receives an explicitly erased post-Typed-HIR view.
- Lower every fully checked module graph into a versioned, sealed `MirGraph` and
  require it for `run`, `build`, and `emit-go`.
- Fingerprint the full immutable AST, imports, function/aggregate contracts, and
  Typed HIR expression types; reject stale or forged backend input with `KS5002`.
- Add `ks mir` plus MIR version/fingerprint fields to JSON check output, while
  keeping the current AST-carrying adapter boundary explicit until normalized MIR.
- Upgrade to MIR schema 2 with typed normalized values, bindings, stores,
  unary/binary operations, calls, explicit basic blocks, and branch/jump/return
  terminators.
- Represent unsupported constructs as visible `ast_fallback` instructions; validate
  block targets and temporary definitions, and include the CFG in the integrity seal.
- Infer direct and transitive capability effects across local call graphs, including
  recursion, and seal deterministic `calls` / `effects` contracts into each MIR
  function.
- Upgrade to MIR schema 3 with deterministic static resource summaries for basic
  blocks, instructions, AST fallbacks, backward edges, and direct self-recursion.
- Include resource summaries in the fingerprint and independently re-derive them
  during seal validation, so forged or stale metadata fails closed with `KS5002`.
- Add fail-closed interpreter runtime budgets to `ks run`: a secure default step
  meter (`KS3601`) plus a user-selectable call-depth ceiling (`KS3602`).
- Count every statement and expression evaluation so empty infinite loops cannot
  evade fuel; keep the existing 512-frame language ceiling as a hard maximum.

The V5 design principle is: **security beyond ambient-authority languages and a
writing experience simpler than Python without hiding dangerous effects.**
