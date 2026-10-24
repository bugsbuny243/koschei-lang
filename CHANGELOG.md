# Changelog

## Unreleased — Core Library v1

- Add the Koschei Core Library: library modules written in Koschei and shipped under `koschei/core_library/`, compiled by the same pipeline as user code instead of duplicated Python/Go host builtins.
- Add `text` (`is_empty`, `is_blank`, `starts_with`, `ends_with`, `strip_prefix`, `strip_suffix`, `before`, `after`, `count`, `replace`, `lines`, `words`) and generic `list` (`is_empty`, `first`, `last`, `concat`, `reverse`, `drop`, `slice`, `insert_at`, `remove_at`, `replace_at`).
- Resolve only registered library names; a project file with a library module's name fails closed with `KS1601` instead of shadowing.
- Reject Core Library modules in Module Lock v1 with an explicit `KS1902` reason.
- Add `ks-core-library` / `koschei.core-library/v1` to list library modules, digests and functions.
- Fix structural equality of `Option`/`Result`/enum values: runtime type evidence no longer takes part in `==`, so `[1].get(0) == Some(1)` and `Some(1) == list.first([1])` are `true`.
- Give `KS3501` Int overflow one text in every executor: the canonical MIR executor and the direct MIR runtime now use the interpreter's message instead of their own short and English variants.
- Make `INT_MIN % -1` an overflow Error in the canonical MIR executor, as it already was in the checked-AST interpreter.
- Render `Option`/`Result`/enum values as `Some(3)` / `None` in the direct MIR runtime instead of the host `EnumValue(...)` representation.
- Rebuild the MIR-Go conformance adapter (v2) on the canonical executor's rules, so `ks build` admits `List<T>`, String/List members, `for` loops, generic functions, imported modules, `or` forms and interpolation, and Core Library programs compile. See `docs/MIR_GO_CONFORMANCE_ADAPTER_V2.md`.
- Fix two v1 native divergences: Int overflow silently wrapped (`3037000500 * 3037000500` printed `-9223372036709301616`) and Floats used Go formatting (`3.0` printed `3`). Binaries now produce the same Error values and the same text as `ks run`.
- Enforce the 512 call-depth limit (`KS3105`) in binaries; structs, `Map`, capabilities, callback members and `to_int`/`to_float` still fail closed with `KS4004`.
- Run every sealed graph without a `MirAstFallback` on sealed MIR under `ks run`; the checked-AST interpreter now only serves graphs that still carry an AST boundary. Programs with member calls but no Option/Result/enum facts no longer get a second semantic authority (an Error inside a list literal stays an element, as in sealed MIR and binaries).
- Let `ks run` reach the language's 512 call-depth limit in every lane: programs stop with `KS3602`/`KS3105` instead of crashing with a Python `RecursionError` after roughly 100 nested calls.
- Add the kernel `sha3_256(text) -> String or Error`: the SHA3-256 digest of the text's UTF-8 bytes from the host's audited implementation (Python `hashlib`, Go `crypto/sha3`), bounded to 1 MiB of input, pure and capability-free. Koschei still implements no cryptographic primitive.
- Add the `secure` Core Library module (`hash`, `digest`, `zero_digest`, `is_digest`): self-describing `sha3-256:` digests with domain separation and length-prefixed fields. The stdlib catalog's `secure.hash` is now `supported`.
- Add `text.unique_sorted` for canonical sets of names.
- Port the Marvel guardians to Koschei as Core Library modules: `captain_marvel`, `hela`, `strange` and `wanda` return the same decisions, reasons and error causes as their Python guardians, and every decision fails closed on a record whose digest no longer matches its fields. Doctor Strange gets its first tests.
- Fix struct aliasing: a field assignment through a `let mut` copy changed every other holder of the same struct, including an immutable `let` binding, a List element and a function's caller. Field assignment now builds an updated copy in every executor.
- Compile non-generic structs with MIR-Go v2: literals, field reads, field assignment, rendering and `==` match `ks run`. Generic structs still fail closed with `KS4004`.
- Render structs as `P { x: 1, name: "a" }` in the direct MIR runtime. `ks run` printed the host representation `_StructValue(type_name='P', ...)` for programs that reached that lane.

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
