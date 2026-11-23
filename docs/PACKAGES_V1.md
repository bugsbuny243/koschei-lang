# Koschei Packages v1 — design proposal

Status: **phase 1 implemented** (0.18.0, `ks pkg`); **phase 2 implemented**
(0.19.0: registry, `ks pkg add`, `publish`, `yank`); **phase 3
implemented** (unreleased: signatures, owners, the public log). Readiness gate 6 for 1.0.0
(`docs/RELEASE_PLAN_AFTER_0_14.md`). Once accepted, its user-facing rules join
`docs/STABILITY_V1.md` before 1.0.0.

## The promise

**Installing or updating a package can never give it new authority without
the application's author seeing it and agreeing to it.**

In Rust, Go, npm or PyPI, a package update can start reading files, calling
the network or running code at build time, and nothing in the update shows
it. In August 2026 three crates.io packages were changed to pull in a
dependency whose build script started a backdoor on every machine that built
them. Koschei Packages are designed so that an update like that is refused
before it is installed.

## What the language already guarantees

These hold today for local imports and stay true for packages:

- **No ambient I/O.** There is no global `read_file` or `http_post`. A library
  function can touch the disk or the network only through a capability token
  it receives as a parameter (`KS1101` otherwise).
- **Capabilities come from `main`.** Only `main(caps: SystemCaps)` receives
  authority, and a caller passes it on explicitly. A function that asks for
  a token the caller does not pass does not compile (`KS1301`).
- **No code runs while compiling.** No build scripts, macros, install hooks or
  compile-time evaluation.
- **Tokens cannot hide.** They cannot be stored in a List or Map, compared, or
  printed as anything but their type.
- **`ks caps`** reports what a program can reach, and `ks caps --deny net`
  fails if it can reach that capability.

So a package update that starts using the network has to add a token to a
function's parameters. The application then no longer compiles until its
author passes that token. Packages v1 turns this from a compile error that
someone might "just fix" into a decision that is shown and recorded.

## Capability surface: computed, not declared

Every package has a **capability surface**: the set of capability kinds
(`disk`, `net`, `env`, `process`, `serve`, `persist`, `input`, `clock`,
`random`, `db`) that appear in the parameters of its exported functions,
directly or through the types they take. A package with an empty surface is
**pure**: no version of it can touch anything outside its arguments.

The compiler computes the surface from the source. The manifest may state it,
but `ks publish` refuses a package whose stated surface differs from the
computed one. A declaration is never trusted on its own.

## Package format

A package is a directory with a `koschei.toml`:

```toml
[package]
name = "onur/arrayref"      # publisher/name; no bare names
version = "0.3.10"
surface = []                # optional; must equal the computed surface

[dependencies]
"acme/hexfmt" = "1.2.0"     # exact versions only in v1
```

The published artifact is the source files and the manifest, nothing else:
no binaries, no scripts. It is identified by the SHA-256 of a canonical
archive.

## Installing

`ks add onur/arrayref@0.3.10`:

1. downloads the archive and checks its SHA-256 against the registry index;
2. checks the publisher's signature (phase 3);
3. type-checks the package and computes its surface;
4. shows the surface, for example `onur/arrayref 0.3.10: pure`, or
   `acme/fetcher 2.0.0: net`;
5. writes the digest **and the surface** into `koschei.lock.json`.

`ks build --locked` already refuses any source byte that differs from the
lock (`docs/MODULE_LOCK.md`); the lock now also covers package archives.

## Updating

`ks update` compares each new version's computed surface with the locked one:

- same or smaller surface: updated, and the change is listed;
- **larger surface: refused.** The output names the package, the versions and
  the new capabilities, for example
  `acme/hexfmt 1.2.0 → 1.2.1 adds: net`. Accepting it takes
  `ks update acme/hexfmt --allow net`, and the lock records that the author
  allowed it.

This applies to transitive dependencies too: a pure package whose new version
pulls in a dependency with `net` widens its own surface and is refused the
same way.

A project can also set a ceiling that no update may pass:

```toml
[policy]
deny = ["net", "process"]
```

## Registry rules

- **Immutable versions.** A published version is never replaced or deleted.
  It can be yanked (hidden from new installs, still installable from a lock).
- **Namespaced names.** `publisher/name`. A new name close to a popular one
  (edit distance 1, swapped characters, look-alike Unicode) is held for
  review.
- **Static index.** The registry serves files: an index and archives. It runs
  no package code, ever.
- **Signatures and a public log (phase 3).** Each release is signed with the
  publisher's Ed25519 key, and every publish is appended to a public log, so
  a release that appears without the publisher can be seen.

## Phase 1 in use

```toml
# koschei.toml of the application
[dependencies]
hexfmt = { path = "../hexfmt" }
fetcher = { git = "https://github.com/acme/fetcher", rev = "<40-hex commit>" }

[policy]
deny = ["process"]
```

```sh
ks pkg sync            # fetch, check, compute surfaces, write the lock
ks pkg sync --allow net  # accept an update that adds net
ks pkg list            # name, version, surface
ks pkg verify          # lock against koschei.toml and every vendored byte
```

- `ks pkg sync` copies each package's `.ks` files and `koschei.toml`, and
  nothing else, into `.koschei/packages/<name>-<digest>/`, and writes
  `koschei.packages.lock.json`. Commit both: builds then need no network.
- Every `ks check`, `run`, `caps` and `build` in the project verifies the lock
  and the vendored bytes first. A missing lock, a `koschei.toml` edited after
  the last sync, a vendored file changed by hand, or an import of a package
  that is not a direct dependency fails with `KS1606`.
- A package cannot receive `SystemCaps`; its surface is what its exported
  functions ask callers for. A package's surface covers the modules it
  imports, so a dependency it declares but never imports does not widen it;
  that dependency's own entry in the lock still guards its surface.
- Git sources take an `https://` URL and a full commit hash; branches and tags
  are refused because they move. Git runs with hooks and submodules disabled.
- Phase 1 has no registry, signatures or version ranges. Two packages that
  need the same dependency from different sources are refused.

## Phase 2 in use

```toml
[dependencies]
hexfmt = { version = "1.2.0" }      # exact version from the registry

[registry]
url = "https://koschei.dev/registry"  # the default; file:// for a local one
```

```sh
ks pkg add hexfmt@1.2.0                       # edit koschei.toml and sync
ks pkg publish ./hexfmt --registry registry    # in a checkout of this repo
ks pkg yank hexfmt@1.2.0 --registry registry
```

- The registry is the `registry/` directory of this repository, served as
  static files by koschei.dev. Publishing is a pull request with the two files
  `ks pkg publish` writes.
- A client checks the archive's SHA-256 against the index, extracts only
  regular `.ks` files and `koschei.toml` (no links, no absolute or `..` paths,
  size limits), checks the package digest, and recomputes the surface. An
  index entry whose surface differs from the computed one is refused, so a
  registry that lies about a package cannot get it past the update rule.
- A yanked version is installed only when the lock already holds it.
- Registry packages can depend only on registry packages.
- Names stay flat in phase 2 (`hexfmt`, not `publisher/hexfmt`): imports use
  the package name, and with one maintainer reviewing every pull request a
  namespace adds little. A new name one edit away from an existing one
  (one letter changed, added or removed, two swapped, `-` for `_`) is
  refused until reviewed with `--allow-similar-name`. Namespaces come back
  with signatures in phase 3.

## Phase 3 in use

```sh
ks pkg keygen ~/.koschei/publisher.key        # once; keep the file private
ks pkg publish ./hexfmt --registry registry --key ~/.koschei/publisher.key
ks pkg sign hexfmt@1.0.0 --registry registry --key ~/.koschei/publisher.key   # versions from before signatures
```

```toml
[policy]
require_signed = true    # refuse unsigned registry packages
```

- **Signatures.** Every new version is signed with the publisher's Ed25519
  key over its name, version, digests, surface and dependencies. The first
  signed version sets the package's `owners`; later versions must be signed
  by an owner. Adding an owner is an edit to the index that a maintainer
  reviews. A signature is never replaced.
- **Signer pinning.** The lock records which key signed each registry
  package. A later sync where a different key (or no key) signed it is
  refused until `--allow-new-signer <package>`: a registry that adds its own
  key as owner cannot slip a version past an existing project.
- **Public log.** `registry/log.jsonl` records every publish, sign and yank;
  each line carries the SHA-256 of the line before it. The client checks the
  chain, requires the index entry to match the log's latest record of it, and
  pins the log head it saw in the lock. A registry that rewrites or drops
  history is refused on the next sync.
- **No dependency.** Ed25519 is implemented in `koschei/ed25519_v1.py` from
  RFC 8032's reference code, checked against the RFC's vectors and OpenSSL
  (`tests/test_ed25519_v1.py`). It is stricter than OpenSSL: small-order
  public keys are refused. Signing is not constant-time; run it on your own
  machine, not on a shared server.
- **Versions published before phase 3** (`hexfmt`, `base64`, `semver`
  1.0.0) are unsigned until an owner runs `ks pkg sign`. They install unless
  `require_signed` is set.

What phase 3 does not do: there is no independent log witness yet, so a
project that has never synced cannot tell a rewritten log from the original;
and a stolen publisher key can sign until the owner list is changed.

## Phases

1. **Pinned sources, no server.** Dependencies by URL or git commit plus
   SHA-256 in `koschei.toml`; surface computation, the lock and the update
   rule. This proves the model before running a service.
2. **Read-only registry.** A static index and archive host, `ks add`,
   `ks update`, `ks publish`, name rules, yanking.
3. **Signatures and the public log.**

## What this does not claim

- A package given `net` on purpose can misuse it. Koschei shows and records
  the grant; it does not judge what the package does with it.
- A pure package can still return wrong data (for example a wrong address to
  a signing function). The surface makes theft impossible, not deception;
  the code that receives the data must check it.
- A compromised publisher key or registry host is out of scope until phase 3,
  and phase 3 makes such an attack visible, not impossible.
- The Go toolchain used by `ks build` stays part of the trusted base.

## Open questions

1. A capability token can be a struct field today (`struct Holder { disk:
   DiskCaps }` checks), and `ks caps` already reports such a package as
   needing `disk` from its caller. The surface computation must follow
   struct types transitively the same way; phase 1 needs tests for nested
   and generic structs.
2. Should a narrowed token (for example disk access to one directory) show in
   the surface as `disk` or as `disk:<path>`?
3. Version ranges: exact versions only in v1, or allow patch ranges once the
   surface rule is in place?
4. Who reviews held look-alike names while the project has one maintainer?
