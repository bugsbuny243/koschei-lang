# Changelog

## Unreleased — Core Library v1

- Multiply, divide and rescale Decimal values: `decimal_mul(a, b, scale, mode)`, `decimal_div(a, b, scale, mode)` and `decimal_rescale(value, scale, mode)` name the result scale and one rounding mode (`down`, `up`, `floor`, `ceiling`, `half_up`, `half_down`, `half_even`) and round once, in integers; an unknown mode is `KS3801`, an overflow `KS3803` and a zero divisor the new `KS3807`. Decimal only added, subtracted and compared before.
- Compile Decimal programs with `ks build`: binaries give the same bytes as `ks run` for every Decimal builtin. `ks build` refused every Decimal program.
- Report decimal text with more than 4300 digits as `KS3803` overflow: Python's integer conversion limit answered instead, with a host message.
- Let a struct field hold a `Decimal`, `Data` or `HttpRequest` in the checked-AST interpreter, which refused the value with "Decimal beklerken Decimal aldı" (`KS3106`).

- Add `ServeCaps.reply_with(status, content_type, headers, body)` and `HttpRequest.cookie(name)` under `ks run` and in native binaries, so a server can set cookies (`Set-Cookie`, several per reply), `Cache-Control` or `Location` and read the cookies a client sends (`docs/SERVE_KNOWHERE_V1.md`). A header is exactly `Name: value` with a token name and a printable ASCII value, so a line break can never smuggle another header; `Content-Type`, `Content-Length`, `Connection` and the hop-by-hop headers stay Koschei's. A refused header gives the client `500` and returns `KS3472`.

- Read JSON: `Data` gets `kind()`, `get(key)`, `at(index)`, `length()`, `keys()`, `text()`, `number()`, `int()`, `bool()` and `is_null()`, and `json_quote(text)` writes a String as a JSON string literal so programs build JSON replies without escaping by hand (`docs/data-language-v1.md`). A read of the wrong kind, a missing key or index, or a number that is not an Int is a `KS3709` Error value. Data used to be parse-and-re-encode only.
- Compile JSON programs with `ks build`: binaries embed the `native/datajson` core when a program uses `parse_json`, `encode_json` or `json_quote`, and give the same bytes as `ks run`. `ks build` refused every JSON program, and the canonical MIR executor stopped with `KS3101` on `parse_json`, so `ks run` failed on any JSON program it could not run on the direct MIR runtime.
- Report the documented `KS370x` codes for JSON failures in every executor: the direct MIR runtime, which runs most small `ks run` programs, printed the codec's internal `KS360x` codes, two of which mean step and call-depth budgets elsewhere. A duplicate key is now quoted as JSON (`"a"`) by both the Python and the Go codec, which used to disagree.

- Add `ServeCaps.reply_as(status, content_type, body)` under `ks run` and in native binaries, so a server can answer JSON or HTML: the reply carries the given `Content-Type` instead of `text/plain; charset=utf-8`. The content type follows `NetCaps.post`'s rule (1–256 printable ASCII characters, no surrounding space), so it cannot add a header; otherwise the client gets `500` and the call returns `KS3472`.

- End the program with the Error that `main` returns in every executor: `fn main()` may `return Error(...)` or pass a failure up with a bare `or return`, and the run prints `KOSCHEI RUNTIME ERROR: <message>` and exits 1. The direct MIR runtime and the checked-AST interpreter did so; the canonical MIR executor (most `ks run` programs) and native binaries stopped with a `KS3401` "capability type-integrity" violation instead, so `return Error("boom")` printed `boom` under `ks run` and `KS3401` from the binary.
- Refuse an `or return` that a function cannot return at check time: in a function without a return type it is `KS1304`, and a bare `or return` that passes an Error up from a function that does not return one is `KS1301`. Both used to pass the checker and stop the program at run time with `KS3401`.

- Add `NetCaps.post(url, content_type, body)` under `ks run` and in native binaries, with `get`'s origin, transport, response and failure rules (`docs/NET_V1.md`). The content type must be 1–256 printable ASCII characters with no surrounding space (`KSNET_CONTENT_TYPE`), so it cannot inject a header; the body is a `String` or `Bytes` of at most 1 MiB (`KSNET_REQUEST_BUDGET`); a `POST` follows no redirect. The checker now refuses a wrong argument count or type for `get` and `post` (`KS1301`) instead of leaving them to the runtime.
- Report a redirect whose `Location` is not a URL as `KS3402` in native binaries too: the broker used `net/http`'s client, which failed such a response with `EIO` before Koschei's redirect rules saw it.

- `DiskCaps.read` and `read_bytes` read regular files only: a FIFO, socket or device is refused with `Dosya okunamadı: düzenli dosya değil: PATH` before it is opened, under `ks run` and in native binaries. Reading a FIFO with no writer used to hang the program, and a Unix socket failed with `ENXIO` instead of being skipped by `secretscan` and `integrity`.
- Compile `Map<String, V>` in native binaries: literals, `get`, `set`, `keys`, `contains`, rendering, `==` and runtime type contracts, with the direct MIR executor's rules (insertion order, a replaced key keeps its position, entries compare in order). `ks build` refused every program that used a map.
- Add two example security tools under `examples/apps/`, tested under `ks run` and as native binaries: `secretscan` reports leaked credentials (private keys, AWS, GitHub, Slack, Stripe and Google keys) by kind, prefix and length without printing them, and `integrity` records SHA3-256 manifests of a directory and reports CHANGED, MISSING and NEW entries. Both may only read the directory they are given and have no network authority; both exit with status 1 when they find something. Neither lets an unchecked file pass: `secretscan` reports a file it cannot scan in full as `not scanned` and fails, and `integrity` refuses a file it cannot digest and a name that holds a newline.
- License Koschei Lang commercially under the Koschei Lang License 1.0 (`LICENSE`, Turkish `LICENSE.tr.md`), replacing the proprietary notice: personal, non-commercial use is free; commercial use needs a one-time, perpetual license that covers versions released within 12 months of purchase (Individual 49 USD, Team 249 USD, Enterprise 999 USD; `LICENSING.md`). Programs written in Koschei and binaries built from them belong to their authors. Earlier MIT-released revisions stay under MIT.
- Add `tools/polar_bundle_v1.py`, which builds the deterministic download sold on Polar (`dist/polar/koschei-lang-<version>.zip`) with the package, installer, license, customer README (`distribution/polar/`), guide, references and examples, and `tests/test_polar_bundle_v1.py`, which runs the bundled Koschei.
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
- Add the Titan value budget (`KS3502`): a String holds at most 16 MiB of UTF-8 and a List at most 1,048,576 items. String `+`, interpolation, `join`, `split`, `push` and `disk.read` produce a `KS3502` Error value instead of a larger value, at the same operation and with the same message in the checked-AST interpreter, the canonical MIR executor, the direct MIR runtime and MIR-Go binaries. See `docs/VALUE_BUDGET_V1.md`.
- Report host memory exhaustion under `ks run` as a `KS3502` runtime stop instead of a raw Python `MemoryError` traceback. Binaries still end with the Go runtime's fatal out-of-memory error.
- Return an Error value from `disk.read` when a file is not valid UTF-8. The host `UnicodeDecodeError` used to end the program, reported as a compiler error and impossible to catch with `or`.
- Add `KOSCHEI_SATISA_HAZIRLIK_V1.md`, the product readiness plan: gates G1–G9 with status, measurable closure conditions and who must close each one.
- Add the `xandar` and `morag` Core Library modules, written in Koschei: `xandar.check` refuses an artifact whose content digest appears in an advisory feed (version labels are never identities, and a malformed feed refuses everything); `morag.check` admits an artifact only within its support window or under a named maintainer's backport for exactly that digest, and refuses unknown or conflicting support.
- Let a local binding shadow a function of the same name in the checked-AST interpreter, as sealed MIR always did. The interpreter resolved the function first and crashed with a host `TypeError`, which kept `secure.hash` (it binds a local named `digest`) off that lane.
- Make `disk.write` atomic (Nidavellir): the text goes to a fresh file beside the target, reaches the disk with `fsync` and replaces the target in one `rename`. A failed or interrupted write now leaves the previous file instead of a truncated, partial one, and a hard link inside the disk scope can no longer redirect a write to a file outside it. Symlink refusal, directory errors and existing permissions are unchanged. See `docs/NIDAVELLIR_ALL_OR_NOTHING_V1.md`.
- Render structs as `P { x: 1, name: "a" }` in the direct MIR runtime. `ks run` printed the host representation `_StructValue(type_name='P', ...)` for programs that reached that lane.
- Add program input (readiness gate G1.2): `caps.input.allow(max_bytes)` gives an `InputCaps` whose `args()` returns the command-line arguments and whose `read_text()` reads standard input to its end, at most `max_bytes` bytes (a static literal up to 16 MiB, shown by `ks caps`). Non-UTF-8 input or arguments, an over-budget input and a failed read are Error values (`KS3430`–`KS3432`). `ks run app.ks a b` hands `a b` to the program; everything after `--` is the program's.
- Let `ks build` compile `main(caps: SystemCaps)` when the program uses only program input: the binary reads `os.Args` and `os.Stdin` and returns the same texts and Error values as `ks run`. Disk, network, environment and every other authority still fail closed with `KS4004`, now naming the native capability broker (G2) as the reason. See `docs/PROGRAM_INPUT_V1.md`.
- Render capability values as their type (`<SystemCaps>`, `<EnvCaps>`, …) in every executor. Printing a token printed the host object with its memory address. Comparing tokens with `==`/`!=` is now refused with `KS2407`, including structs that carry one.
- Add clock and random capabilities (readiness gate G3): `caps.clock.allow(resolution_ms)` gives `now_ms()` and `monotonic_ms()` rounded down to a static resolution; `caps.random.allow(max_bytes)` gives `hex(count)` and `below(bound)` from the operating system's secure source (Python `secrets`, Go `crypto/rand`) under a per-token byte budget (`KS3450`/`KS3451`). Both compile into native binaries. See `docs/CLOCK_RANDOM_V1.md`.
- Add the language guide in English and Turkish (`docs/guide/`): every program in it is run by the test suite and must print the documented output under `ks run` and, where the native backend admits it, from the binary.
- Generate `docs/reference/ERROR_CODES.md` (every diagnostic, both languages) and `docs/reference/CORE_LIBRARY.md` from their sources with `python -m koschei.reference_docs_v1 --write`; a test fails when either is stale.
- Add three end-to-end example applications under `examples/apps/` (`wordfreq`, `release_gate`, `keygen`), each tested under `ks run` and as a native binary.
- Give `String.to_int` one rule in every executor and compile it natively: trimmed text, an optional sign and ASCII digits, within signed 64 bits. The interpreter used Python's `int()`, which also accepted `1_000` and non-ASCII digits and returned values beyond Int.
- Add the stability policy proposed for 1.0 (`docs/STABILITY_V1.md`), the threat model with evidence per threat (`docs/THREAT_MODEL_V1.md`) and a measured benchmark dossier against Python, Go and Rust (`bench/compare/run_v1.py`, `docs/benchmarks/`).
- Add the buyer-facing `SALE_PACKAGE_V1.md` and the owner's action list `KOSCHEI_SAHIP_EYLEM_LISTESI_V1.md`.
- Make native builds byte-reproducible: `ks build` passes `-trimpath`, `-buildvcs=false` and an empty build id to Go. The temporary workspace path used to end up in the binary, so no two builds of the same source were identical.
- Add `install.sh`: installs Koschei into its own virtual environment and links `ks`.
- Add the `Bytes` type (readiness gate G1.3): `text.to_bytes()`, `length`, `hex`, `to_text`, `get`, `slice`, `+`, byte-wise comparison, `bytes_from_hex`, `sha3_256_bytes` and `secure.hash_bytes`; binary data from `InputCaps.read_bytes()`, `DiskCaps.read_bytes(path)` and `RandomCaps.bytes(count)`. A `Bytes` value holds at most 16 MiB. Every executor and MIR-Go binaries agree. See `docs/BYTES_V1.md`.
- Add the multi-request loopback server (readiness gate G4): `server.accept()` returns an `HttpRequest` (`method`, `path`, `header`, `body`, `body_bytes`) and `server.reply(status, body)` answers it. Knowhere: one request per connection, an unanswered request is closed with 500 (`KS3470`), nothing carries over. Sakaar: raw path and headers, no implicit parsing. Every budget is per request; protocol and budget failures are answered and the server keeps listening. `ks run` only; native builds refuse it with `KS4004`. See `docs/SERVE_KNOWHERE_V1.md`.
- Add the native capability broker (first step of readiness gate G2): binaries that read the disk or the environment run as a broker that holds the authority and a worker that runs the program with an empty environment under a seccomp filter (no file opens, sockets, exec, fork or file-system changes). Read-only disk and `env.get` answer exactly like `ks run`; disk writes and the network stay refused. linux/amd64. See `docs/NATIVE_BROKER_V1.md`.
- Let native binaries write and delete through the broker (second step of G2): `DiskCaps.write`, `write_file` and `delete` replace files atomically, keep the target's permission bits, refuse symlinks, directories, missing parents and the scope root, and give the same Error texts and the same resulting tree as `ks run`. The network stays refused.
- Let native binaries use the network through the broker (third step of G2), and give `NetCaps.get` one set of rules in every executor (`docs/NET_V1.md`): a strict URL grammar (no user information, no host-dependent parsing), Koschei follows redirects itself (five at most, never outside the origin), every final status is a `Response` instead of a host `HTTP Error` text, the body must be complete and UTF-8, failures are `API isteği başarısız: <CODE>: <url>`, proxies are chosen by one rule from the environment, and requests send `User-Agent: koschei/1` instead of the host's Python version. `Response` prints as `<Response>`.
- Let native binaries run the multi-request loopback server (G4) through the broker: the broker owns the listener and the pending connection and ports the effective request grammar, the budgets, the Knowhere rule and every Error text; clients read the same bytes from `ks run` and the binary. Under both, socket failures now name codes (`KS3411: listener failed: EADDRINUSE`) instead of host messages, header names must be tokens and `request.header()` folds ASCII letters only, and a bind's port must be ASCII digits with `::1` the only IPv6 loopback. A dropped server closes its listener and unanswered connection in the binary as under `ks run`, so a server opened anew each round of a loop keeps its bind.
- Confine the native worker with a seccomp allow list instead of a deny list: only the system calls the Go runtime and the program need (measured by tracing confined workers) pass; `clone` must create a thread, `kill`/`tgkill`/`prlimit64` may only reach the worker itself, `clone3` is `ENOSYS`, and every other call is `EPERM`. glibc's per-thread `rseq`, `set_robust_list` and `set_tid_address` are listed, so binaries that link it (cgo's resolver) no longer abort intermittently when glibc starts a thread.
- `text.lines` and `text.words` return `Result<List<String>, Error>`: a value with more pieces than one List may hold is an `Err` the caller handles with `or`, instead of a silently shortened list. `text.count`, `text.replace`, `text.before`, `text.after` and `secure.is_digest` also stay within the List budget, and prefix/suffix tests compare UTF-8 bytes.
- Make disk errors host-independent: they name the errno (`ENOENT: root/missing`) instead of the host's `[Errno 2] ...` text. `disk.read` no longer translates `\r\n` to `\n`, checks the 16 MiB budget before UTF-8, and a path containing NUL is outside the scope instead of crashing; `list` requires UTF-8 names and `env.get` a UTF-8 value.

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
