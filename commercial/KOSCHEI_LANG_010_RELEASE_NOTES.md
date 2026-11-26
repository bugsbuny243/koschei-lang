# Koschei Lang 0.26.0 — Release Notes

**Product:** Koschei Lang (independent of Koschei Sentinel and Web3 Hub)  
**Version:** 0.26.0  
**Release line:** commercially licensed, pre-1.0 language/toolchain

## New in 0.26.0

- **Hardening: every broker domain is pinned.** Server bind addresses and
  persistence files now join disk directories, environment variables and
  network origins. When the program names them with string literals, the
  native broker refuses any other. Persistence files are compared in
  canonical form.

## New in 0.25.0

- **Hardening: literal scopes are pinned.** When a program names its disk
  directories, environment variables or network origins with string literals,
  the native broker refuses every other one. A compromised worker cannot
  reach outside what the source names. Prefixes computed at run time are not
  pinned.
- **Fix:** since 0.22.0 a native program that created a disk token and never
  used it failed with `KS5002`, while `ks run` accepted it. Fixed.

## New in 0.24.0

- **Security fix: the ownership checker.** A move in a `while` condition was
  checked as if the condition ran once, so `while n < 2 && takes(tok)` could
  hand the same capability token out on every iteration. Such a move is now
  refused with `KS3932`. An ownership soundness fuzzer found this.
- **Ownership model specified (1.0 gate 4 closed).**
  `docs/OWNERSHIP_MODEL_V1.md` states the rule. `tools/fuzz/affine_fuzz.py`
  checks the checker against an independent path-exhaustive oracle on every
  pull request and nightly. Six of the seven 1.0 gates are now closed; the
  independent review remains.

## New in 0.23.0

- **Security fix: upgrade if you install packages from a registry.** The
  client read a version's yank state only from the registry index. A registry
  that rolled its index back after an owner yanked a bad release could serve
  that release to new installs, although the public log recorded the yank. The
  client now reads yank state from the hash-chained log and refuses an index
  that disagrees. A formal model (TLA+) found this gap.
- **Formal models complete.** The package update rule, broker confinement
  and the registry log are all model-checked with TLC (`formal/tla`).

## New in 0.22.0

- **Security fix: please upgrade if you build native binaries that use the
  disk, the environment, the network or the server.** The capability broker
  served disk and environment requests to any worker. A worker that was
  compromised could ask for a writable directory, or read environment
  variables, secrets included, even in a program that only read files or only
  used the network. Seccomp still applied. The broker now serves only the
  authority the compiler saw the program create, and ends the conversation on
  anything else. A formal model (TLA+) found this gap.
- **Formal models.** `formal/tla` holds TLC-checked models of the package
  update rule and of broker confinement. For each model, every check in the
  code is shown to be necessary: switching it off gives a counterexample.

## New in 0.21.0

- **Security fix — please upgrade if you use `ks workspace build`.** Native
  binaries built from a workspace used the legacy backend, which runs disk,
  network, server and persistence effects inside the program's own process,
  without the capability broker and seccomp confinement that `ks build`
  enforces. Workspace builds now use the confined backend and refuse
  (`KS4004`) anything it cannot confine. Single-file `ks build` was not
  affected.
- **Persistence and one-shot serving in native binaries.** `PersistCaps`
  (`caps.persist.allow`, `load`, `commit`) and `ServeCaps.exchange` now run
  through the broker with the interpreter's exact behaviour and error texts.
  Every program in the repository and every workspace `main` builds
  natively; 1.0 gate 2 is closed.
- The three registry packages are signed by their owner.

## New in 0.20.0

- **Signed packages and a public log.** `ks pkg keygen`, `ks pkg publish
  --key`, `ks pkg sign`. Versions are signed with Ed25519 by the package's
  owners. Your lock remembers who signed each package: a version signed by
  someone else is refused until you pass `--allow-new-signer <package>`.
  `registry/log.jsonl` is a hash-chained record of every publish, sign and
  yank; your lock pins the part you have seen, so a registry that rewrites
  history is refused. `[policy] require_signed = true` refuses unsigned
  packages. Ed25519 is implemented without dependencies (RFC 8032, checked
  against OpenSSL); Koschei still installs nothing else.
- **Fuzzing.** `tools/fuzz/` attacks the toolchain with mutated and generated
  programs, capability misuse at random depth, disk escape attempts, and
  malformed package files. Two package-lock bugs it found are fixed. A small
  batch runs on every pull request.
- **Audit brief.** `docs/AUDIT_SCOPE_V1.md` lists the seven claims an
  independent reviewer should try to break; the threat model covers
  packages, the registry and signatures.
- **1.0 gates** are tracked in `docs/RELEASE_PLAN_AFTER_0_14.md`;
  self-hosting is scoped out of 1.0.

## New in 0.19.0

- **Package registry** (`ks pkg add name@version`, `ks pkg publish`,
  `ks pkg yank`, and `{ version = "x.y.z" }` dependencies). The registry is
  static files at `https://koschei.dev/registry/`; publishing is a pull
  request. The client checks the archive and package digests, extracts only
  `.ks` sources, and recomputes each package's capability surface, refusing
  an index that disagrees. Versions are immutable, yanked versions install
  only from an existing lock, and look-alike names are held for review.
- **First packages**, all pure: `hexfmt` 1.0.0, `base64` 1.0.0, `semver`
  1.0.0. Try `ks pkg add base64@1.0.0`.
- **`KS1402`:** a List, Map, String or Bytes method whose result is thrown
  away (`items.push(x)` on its own line) no longer compiles. These values are
  immutable, so the line did nothing.
- `"x".bytes()` now reports an unknown method (`KS1502`, suggesting
  `to_bytes`) instead of `KS1306`.

## New in 0.18.0

- **Package dependencies with locked capability surfaces** (`ks pkg sync`,
  `ks pkg list`, `ks pkg verify`). Dependencies come from a path or a git
  commit. The compiler computes each package's surface (which of disk, net,
  env, … its functions ask callers for) and locks it with the package's
  SHA-256. An update that adds a capability is refused until you pass
  `--allow <capability>`; `[policy] deny` refuses a capability outright; a
  vendored package changed after locking does not compile (`KS1606`). No
  registry yet: this is phase 1 of `docs/PACKAGES_V1.md`.
- **Supply-chain demo** (`examples/supply_chain_demo`): the same compromised
  dependency in Rust and Koschei, including an update that `cargo build`
  takes without a question and `ks pkg sync` refuses.
- **Stability policy approved** (`docs/STABILITY_V1.md`); it takes effect
  with 1.0.0.
- **Hardened native builds:** `ks build` pins Go's environment
  (`GOFLAGS`, `GOENV`, `GOPROXY`, `GOTOOLCHAIN`, `GOWORK`, `CGO_ENABLED`), so
  a hostile environment cannot inject a `-toolexec` hook or fetch modules.

## New in 0.17.0

- `ks build` compiles almost every program `ks run` runs. New in native
  binaries: more List/Map methods (`sum`, `min`, `max`, `unique`, `flatten`,
  `chunks`, `partition`, `scan`, `merge`, `add`, …), Data (`parse_json`,
  `encode_json`, `json_*`), exact decimals, generic and typestate structs,
  bounded queues, task scopes and `parallel_map`. Output and error messages
  match `ks run`. Of the repository's programs, one still needs `ks run`
  (it uses `PersistCaps`).
- `sha256_bytes(data)`: SHA-256 beside `sha3_256_bytes`, from the host
  library.
- Library modules that reproduce the Python guardians byte for byte:
  `vormir` (sacrifice before rebirth), `galaxy_identity` (Veyra and Aevra)
  and `matrix_reality` (Matrix, Hara and admission). Differential tests
  compare them with the Python modules under `ks run` and as binaries.
- Fixes: `json_int` on very large or exponent numbers no longer stops
  `ks run` with an internal error; the Go and Python JSON cores report
  errors identically; a false `KS2401` on List/Map elements is gone.

## New in 0.16.0

- `ks build` compiles `List.sort()`, `filter`, `find`, `map` and `any`.
  Programs that used them ran under `ks run` but did not build; now the
  binary gives the same results and errors. A callback is a top-level
  function of one parameter or a lambda, as in `ks run`.
- When validation fails, its output names the failing tests instead of
  showing only the last lines.

## New in 0.15.0

- Servers no longer stall behind idle clients. Requests are read beside
  the program (up to 128 at a time per server); a client that connects and
  sends nothing occupies one reader, not the server. Three idle connections
  used to delay every other request by 30 s.
- `ks build` always produces a static binary, so it starts on any
  linux/amd64 host, including Alpine and images that hold only the binary.
- `ks caps` prints the manifest in your language (`--lang en|tr`, English
  by default); `--json` is unchanged.
- Fixes: a `Map` taken out of a `List` with `or` no longer triggers a false
  KS2401, and errors in an imported module name that module.

## New in 0.14.0

- `ks run` is about twice as fast: a million-iteration loop drops from
  8.5 s to 3.5 s. Results, Error values and step counts are unchanged.
- Lambdas: `xs.filter(fn(x: Int) -> Bool { return x > 0 })`. A lambda does
  not capture variables of the enclosing function, so it can never quietly
  hold a capability.
- Generic structs work with annotations (`let page: Page<Int> = ...`) and
  in generic functions that swap type parameters; type mismatches print
  source types such as `Pair<Int, String>`.

## New in 0.13.0

- A database: `caps.db.allow(path, max_rows, max_bytes, deadline_ms)`
  opens one SQLite file; `exec(sql, params)` changes rows and
  `query(sql, params)` returns them as `Data`. SQL must be a string literal
  and values bind to `?` placeholders, so SQL injection cannot be written.
  `ATTACH`, `PRAGMA` and extensions are refused; rows, file size and
  statement time are bounded. Works under `ks run`; `ks build` refuses it
  for now. See `docs/DB_V1.md` in the source repository.

## New in 0.12.0

- Public servers: `caps.serve.allow("0.0.0.0:8080", ...)` (or `[::]:PORT`)
  listens on every interface, so a Koschei web application can be reached
  from other machines. Budgets, the strict HTTP grammar and one request per
  connection are unchanged; other non-loopback addresses are refused.
- The `http` Core Library module: `route` matches `/users/:id`, `query`
  and `params` read query strings and form bodies, `cookies` reads a
  `Cookie` header and `escape_html` makes text safe for a page.
- `server.reply_with(status, headers, body)` sends response headers such
  as `Location` and `Set-Cookie`; redirects (301, 302, 303, 307, 308) and
  401 are allowed. A header value can never add another header.

## New in 0.11.0

- Read JSON: `json_kind`, `json_has`, `json_get`, `json_at`, `json_text`,
  `json_int`, `json_float`, `json_bool`, `json_length`, `json_keys` and
  `json_items` read the `Data` value `parse_json` returns. A missing member
  or a value of the wrong kind is an Error value, never a crash.
- Write JSON: the `json` Core Library module builds JSON text with every
  quote, backslash and control character escaped.
- `math`: `min`, `max`, `clamp`, `abs`, `pow`, `gcd` and Float variants.
  A result outside 64-bit Int is an Error value, never a wrapped number.
- `time`: UTC timestamps to dates and back, and ISO 8601 text, for
  years 1 to 9999. An impossible date is an Error value.
- `parse_json` now works in programs that import modules.

## New in 0.10.1

- `ks-mcp` (also `uvx koschei-lang`): an MCP server that lets an AI agent
  run Koschei programs under a capability policy you set once on its
  command line. A program that asks for more is rejected before it runs.
  See `docs/MCP_SERVER.md` in the source repository.
- Restored release-trust tooling: `ks maturity`, `ks maturity-attest`,
  `ks release-proof`, `ks build-compare` and `ks build-compare-verify`.
- Also on PyPI: `pip install koschei-lang`. PyPI files carry Sigstore
  provenance tied to the source repository's publishing workflow.

## Included

- `ks check` — compile-time diagnostics and explicit capability checks.
- `ks caps`, `ks caps --deny <domain>` — whole-program
  capability manifest and CI policy, including imported `.ks` modules.
- `ks run` — checked interpreter.
- `ks build` — native build using the current Go backend adapter.
- `ks fmt`, `ks lsp`, `ks explain` — developer tools.
- Typed `Option` and `Result`, explicit errors, bounded
  String/List values and Koschei-authored Core Library modules.
- Shipped example apps for secret-pattern scanning and directory
  integrity snapshots, with read-only disk authority and no network.
- A non-executed supply-chain example: unauthorized disk usage
  in an imported module is rejected with `KS2401`.
- English and Turkish language guides, generated Core Library and
  error-code references, licensing and customer installation guide.

## Installation

The included `install.sh` targets Unix-like environments using a shell,
Python 3.12+ and a virtual environment. Go 1.24+ is required only
for native `ks build`.

```sh
./install.sh
ks version
ks run examples/hello.ks
ks check examples/supply_chain/main.ks # expected KS2401, exit code 1
```

Do not run arbitrary third-party installer scripts or
untrusted interview coding projects as a security test.
The installer does not make the host operating system a sandbox.

## Licensing

Personal non-commercial use is free. A commercial license is a
one-time purchase of $49 per developer; an organization buys one
license for each developer who uses Koschei commercially. Purchased releases
can be used perpetually; releases in the next 12 months
are included. The authoritative terms are in `LICENSE`,
`LICENSING.md` and their Turkish versions.

## Known limits

This is 1.0-predecessor software, not a completed self-hosted
compiler. The source interpreter and Go native adapter require
their documented host dependencies. Do not interpret Koschei
capability security as protection for arbitrary code executed
outside Koschei, compromised endpoints, stolen credentials,
AI agent misuse, on-chain signing or wallet custody.
No independent bank/exchange production certification is claimed.

## Release authenticity

Verify the supplied ZIP against the SHA-256 value delivered
through an independently authenticated publisher channel.
A hash supplied only alongside an untrusted download is not
proof of provenance. Customer updates, refund and support
arrangements are governed by the seller's published terms.
