# Koschei (`.ks`)

## Product direction and joint packages

Koschei Lang is an independent programming language and library ecosystem for cybersecurity-centered general-purpose software development. Its own semantics, compiler, standard library and runtime define the product; Web3 and agent integrations are applications of the language. Self-contained distribution and surpassing Rust in security remain development goals requiring executed evidence.

**Koschei Lang and Koschei Sentinel are offered together in the same commercial packages.** Their runtime dependencies and release gates remain independent. See [product direction](docs/PRODUCT_DIRECTION_2026-09-10.md) and the [offline bundle contract](docs/COMMERCIAL_BUNDLE_V1.md).

> **Private commercial development repository. Koschei is proprietary software. Access to this repository does not grant redistribution, sublicensing, resale, or publication rights. See `LICENSE`.**

**A capability-secure programming language. An imported package cannot touch your disk, network, or environment unless you hand it a token.**

Most supply-chain attacks work because a dependency inherits every permission the process has. Install a package, and it can read `~/.ssh`, your `.env`, or open a socket — without asking. Koschei removes that ambient authority: side-effect access is a value that must be passed in, and the compiler rejects a program that reaches for authority it was never given.

Türkçe: [README.tr.md](README.tr.md)

---

## Internal development quickstart

This repository is private. The commands below are for authorized collaborators and licensed development environments only.

```bash
git clone <authorized-private-koschei-repository>
cd koschei-lang
pip install .
ks check examples/supply_chain/main.ks
```

A deliberately malicious package in `examples/supply_chain/analytics.ks` tries to read a secrets file and return it to the caller. The expected result is compile-time rejection:

<!-- verify: expect KS2401 -->
```ks
fn track(event: String) -> String or Error {
    let secret = disk.read("/etc/app/secrets.env") or return Error("unreadable")
    return secret
}
```

Expected output:

```text
KOSCHEI ERROR: KS2401 [line 6, column 18]: Required capability is unavailable
in this scope — A disk, network, environment, or process operation was
attempted without the corresponding capability token.
Hint: run 'ks --lang en explain KS2401' for details.
```

Exit code `1`. The program never ran. The file was never opened. Nothing was sent anywhere.

This is not a runtime sandbox catching the call. `disk` does not exist inside `track` at all, so the attack fails at compile time.

---

## Distribution and installation

Koschei is not distributed as an unrestricted public source package. Development builds are installed from authorized private source or an approved licensed artifact channel.

For an authorized source checkout:

```bash
pip install .
ks version
```

Your first program:

```bash
ks new hello-koschei
cd hello-koschei
ks run .
```

`ks new` creates a zero-dependency project with a `koschei.toml` and `src/main.ks`. Commands accept a source file, a project directory, or a `koschei.toml` path.

---

## Core ideas

- **No ambient authority.** Disk, network, environment, and process access require an explicit capability value. A function that was not passed one cannot perform the effect.
- **Capabilities narrow, never widen.** `caps.disk` is a root token that can only delegate; `caps.disk.allow(path)` produces a narrowed token that cannot re-widen (`KS2403`) and a root token cannot perform I/O directly (`KS2402`).
- **No `null`.** Values that may be absent are `Option<T>` (`Some` / `None`).
- **Errors are values.** `Result<T, E>` with a single `or` keyword in three forms: `or return`, `or default`, `or { block }`. An unhandled error value is a compile error (`KS1401`).
- **Immutable by default.** Rebinding requires `let mut`.
- **Every diagnostic is explainable.** 33 error codes with a bilingual catalog; `ks explain KS2401` prints the cause and a fix.

## Example

<!-- verify: compile — requires an external HTTPS origin at runtime -->
```ks
fn fetch_data(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("request failed")
    return response.text()
}

fn main(caps: SystemCaps) {
    let api_net = caps.net.allow("https://api.example.com")
    let response = fetch_data(api_net, "https://api.example.com/v1")
    println(response)
}
```

`fetch_data` can reach exactly one origin. It cannot touch the disk, read an environment variable, or start a process — not because it was audited and found not to, but because it holds no token that would let it.

## The capability manifest

Because authority is explicit in the source, it can be summarized mechanically. `ks caps` reports everything a program is able to reach, across the whole module graph:

```bash
ks caps examples/app.ks
ks caps --json src/main.ks
ks caps --deny net src/main.ks   # exits 2 if the program can reach the network
```

For a pure program the manifest is empty, and that is a checkable fact rather than a claim in a code review:

```text
KOSCHEI CAPABILITY MANIFEST: examples/app.ks

This program carries no side-effect capability.
No disk, network, environment, or process access — pure computation.
```

The `--deny` gate is designed for CI: a build fails if a dependency update silently adds reach.

## Language features

Implemented today: functions with typed parameters, inferred generic functions, generic structs and enums, `let` / `let mut`, structs, `List<T>`, immutable `Map<String, V>` (`get`/`set`/`keys`/`contains`), `for`-in, `if`/`else`/`while` with `Bool`-only conditions, enums with exhaustive `match`, real `Option<T>` / `Result<T, E>`, full expression interpolation (`"{items.length()}"`), a daily standard library (`String` `trim`/`split`/`join`, `List` `sort`/`filter`/`contains`), and a module system where `import risk` binds `risk.ks` next to the importing file — no manifest, no build script, no config.

## Toolchain

```bash
ks check src/main.ks          # types, modules, capability rules
ks run src/main.ks            # interpreter
ks build src/main.ks -o app   # current native build path
ks fmt --write src/           # canonical formatting
ks caps src/main.ks           # capability manifest
ks explain KS2401             # diagnostics, --lang tr for Turkish
ks check --json src/main.ks   # stable code/message/line/column for editors
ks mir src/main.ks            # sealed checked backend contract
ks lsp                        # zero-dependency language server
ks tokens / ks ast
```

Koschei's long-term canonical architecture is defined by Koschei semantics and verified execution contracts, not by the implementation language of temporary bootstrap/tooling layers. External adapters are non-authoritative interoperability mechanisms.

## Editor support

`editors/vscode` contains the official zero-dependency LSP extension: `.ks` syntax highlighting, live diagnostics, formatting, hover, go-to-definition, document symbols, and completion. The server is available through `ks lsp` (with `ks-lsp` kept as a compatibility alias).

## Tests

```bash
python -m unittest discover -s tests -v
```

The CI suite includes compiler/runtime tests, native/interpreter parity checks, repository documentation examples, committed golden outputs, capability-security regression tests, and deception-plane attack simulations.

## Status

Koschei is pre-1.0 and under active private commercial development. Syntax, runtime contracts, licensing, distribution, and security architecture may change before the first production release. Do not put it in production yet.

Security boundaries currently enforced in the native path include capability denial, narrowed authority, path traversal/symlink escape protection, read-only enforcement, redirect-origin enforcement, call-depth bounds, opaque protected-source object identity, epoch-scoped alias rotation, decoy source views, and epoch-bound read grants. Security claims must continue to be backed by tests and evidence; the project does not claim that any software system is mathematically impossible to compromise.

The protected-source/deception architecture is being hardened through staged attack waves. Canonical source identity remains separate from physical source locators, and decoy views are non-deployable by construction.

## Commercial development

Koschei is being developed as proprietary commercial software. Public redistribution of the current repository, compiler/runtime security implementation, deception mechanisms, model integrations, or derivative commercial products is not authorized unless a separate written license expressly permits it.

Future customer-facing distribution may include licensed SDK/tooling, signed binaries, private package/artifact channels, enterprise policy management, audit evidence, and support/SLA offerings. Those distribution rights will be defined by separate commercial terms rather than repository access alone.

## Contributions

Contributions are accepted only through authorized private collaboration. Before accepting external code into the proprietary core, contributor/IP terms must be established so ownership and commercial licensing rights remain unambiguous.

## License

**Proprietary — all rights reserved for current and future proprietary Koschei revisions.** See `LICENSE` for the historical MIT notice covering only revisions previously released under MIT and for the current proprietary terms.
