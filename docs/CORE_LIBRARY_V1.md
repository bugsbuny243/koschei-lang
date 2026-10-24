# Koschei Core Library v1

Status: **first library modules written in Koschei; `ks run` and `ks build`**

This is the everyday layer of the Koschei library. The four library universes
(Marvel, Matrix, quantum physics, other universes) that build on it are mapped
in [`KOSCHEI_KUTUPHANE_EVRENLERI_V1.md`](../KOSCHEI_KUTUPHANE_EVRENLERI_V1.md).

## Why

Until now every standard-library operation was a host builtin: each new
`String` or `List` method needed a Python interpreter implementation, a
generated Go runtime implementation and Typed HIR wiring, all kept in parity by
hand. That makes the library a property of the bootstrap host, not of Koschei.

The Core Library reverses that direction. Its modules are ordinary `.ks` source
shipped with the toolchain under `koschei/core_library/`. They are parsed,
type-checked, effect-checked and lowered by the same compiler pipeline as user
code, so each library function has exactly **one** implementation, written in
Koschei.

This is step 2 of the independence path: the library moves into the language
first, and a small host kernel (`length`, `contains`, `trim`, `split`, `join`,
`get`, `push`, `take`, `sha3_256`) remains below it until the compiler hosts
itself.

## Using it

```ks
import text
import list

fn main() {
    let line = "ka:vor:shi"
    let name = text.before(line, ":") or "?"
    let roots = text.replace(line, ":", " ") or line
    println("{name} | {roots} | {text.ends_with(line, "shi")}")

    let values = [3, 1, 2]
    let head = list.first(values) or 0
    println("{head} {list.reverse(values)} {list.drop(values, 1)}")
}
```

`ks-core-library` (or `python -m koschei.core_library_v1`) lists every module,
its SHA-256 digest and its public functions; `--json` emits the
`koschei.core-library/v1` schema.

## Modules

### `text`

| Function | Result | Meaning |
|---|---|---|
| `is_empty(value)` | `Bool` | no characters |
| `is_blank(value)` | `Bool` | only whitespace |
| `starts_with(value, prefix)` | `Bool` | an empty prefix always matches |
| `ends_with(value, suffix)` | `Bool` | an empty suffix always matches |
| `strip_prefix(value, prefix)` | `Option<String>` | `None` when the prefix is absent |
| `strip_suffix(value, suffix)` | `Option<String>` | `None` when the suffix is absent |
| `before(value, separator)` | `Option<String>` | text before the first occurrence |
| `after(value, separator)` | `Option<String>` | text after the first occurrence |
| `count(value, needle)` | `Result<Int, Error>` | non-overlapping, left to right |
| `replace(value, old, replacement)` | `Result<String, Error>` | every non-overlapping occurrence |
| `lines(value)` | `List<String>` | split on `\n`, one trailing `\r` removed, no extra final empty line |
| `words(value)` | `List<String>` | non-empty pieces between spaces, tabs, `\r`, `\n` |
| `unique_sorted(values)` | `List<String>` | distinct values in ascending code-point order: a canonical set of names |

A pattern that must locate something (`separator`, `needle`, `old`) may not be
empty. An empty pattern has no single meaning, so the function returns `None`
or an `Error` value rather than guessing.

`ends_with` and `strip_suffix` are exact even when the suffix overlaps itself
(`"aaa"` ends with `"aa"`). `split` matches left to right without overlap, so
the implementation recovers the true trailing match with a recursion whose
value argument strictly shrinks; the derivation is documented in
`koschei/core_library/text.ks`.

### `list`

All functions are generic over the item type and never mutate their input.

| Function | Result | Meaning |
|---|---|---|
| `is_empty(items)` | `Bool` | no items |
| `first(items)` / `last(items)` | `Option<T>` | `None` for an empty list |
| `concat(left, right)` | `List<T>` | left items, then right items |
| `reverse(items)` | `List<T>` | items in reverse order |
| `drop(items, count)` | `List<T>` | skips `count` items, mirroring `List.take` |
| `slice(items, start, end)` | `Result<List<T>, Error>` | requires `0 <= start <= end <= length` |
| `insert_at(items, index, item)` | `Result<List<T>, Error>` | requires `0 <= index <= length` |
| `remove_at(items, index)` | `Result<List<T>, Error>` | requires `0 <= index < length` |
| `replace_at(items, index, item)` | `Result<List<T>, Error>` | requires `0 <= index < length` |

Out-of-range indices produce an `Error` value; they are never clamped silently.

### `secure`

Written in Koschei over the kernel `sha3_256(text) -> String or Error`, which
delegates to the host's audited SHA3-256 (Python `hashlib`, Go `crypto/sha3`).
Koschei implements no cryptographic primitive (`crypto_agility_v1`). The
kernel digests the UTF-8 bytes of its input, returns 64 lowercase hex
characters, and returns an `Error` value for more than 1 MiB of input. It is
pure (allowed in `pure fn`) and needs no capability.

| Function | Result | Meaning |
|---|---|---|
| `hash(value)` | `Result<String, Error>` | `"sha3-256:"` + hex digest of `value` |
| `digest(context, parts)` | `Result<String, Error>` | domain-separated digest; `context` may not be empty |
| `zero_digest()` | `String` | the all-zero digest: "no previous record" at the start of a chain |
| `is_digest(value)` | `Bool` | `value` has exactly the shape this module produces |

`digest` encodes `koschei.secure.digest/v1`, then the context and every part
as `<length>:<text>` (lengths in characters) on their own lines, so two
different `(context, parts)` inputs never encode to the same bytes. Digests
name their algorithm, so a later algorithm can live beside this one.

```ks
import secure

fn main() {
    let id = secure.digest("koschei.example.order/v1", ["S-0001", "40"]) or "?"
    println("{secure.is_digest(id)} {secure.is_digest("abc")}")
}
```

### Marvel universe: `captain_marvel`, `hela`, `strange`, `wanda`

The first library universe modules written in Koschei. Each one ports a Python
guardian and returns the same decisions, reasons and error causes; the
mapping, rules and status live in
[`KOSCHEI_KUTUPHANE_EVRENLERI_V1.md`](../KOSCHEI_KUTUPHANE_EVRENLERI_V1.md).

| Module | Records | Functions |
|---|---|---|
| `captain_marvel` | `BlastRadiusBudget`, `PropagationVerdict` | `issue_budget`, `evaluate`, `is_canonical_budget` |
| `hela` | `AuthorityTombstone` | `bury`, `remains_dead`, `is_resurrection_attempt`, `is_canonical` |
| `strange` | `FutureStep`, `FutureVerdict` | `simulate` |
| `wanda` | `RealityCommitment` | `commit`, `extends`, `detects_fork`, `detects_rollback`, `is_canonical` |

```ks
import strange

fn main() {
    let steps = [
        FutureStep { effect: "read", target: "disk", authority_before: ["disk", "net"], authority_after: ["disk"] },
        FutureStep { effect: "send", target: "socket", authority_before: ["disk"], authority_after: ["disk", "net"] },
    ]
    let verdict = strange.simulate(steps, 8, []) or return
    println("{verdict.safe} {verdict.first_violation} {verdict.reason}")
}
```

- Every decision function re-derives the digest of each record it receives.
  A record edited after it was issued, or built by hand, gets the fail-closed
  answer. A digest is not a signature: it proves that the fields did not
  change, not who issued the record.
- Digests use `secure.digest` with one context per record kind, so they differ
  from the Python byte layout by design.
- Struct names are global within a program: importing one of these modules
  reserves its record names, and a project struct with the same name fails
  closed with `KS1604`.
- Koschei v1 has no private functions, so helpers such as `strange.verdict`
  are visible too.
- Re-deriving digests costs `ks run` steps (see `--max-steps`); native
  binaries are not metered.

## Resolution and security rules

- Only the names registered in `CORE_LIBRARY_MODULES_V1` (`captain_marvel`,
  `hela`, `list`, `secure`, `strange`, `text`, `wanda`) are library modules. A stray `.ks` file placed in the library directory is never
  importable by user code.
- A project file with the same name as a library module (for example a
  `text.ks` next to `main.ks`) makes `import text` ambiguous. The import fails
  closed with `KS1601` instead of silently shadowing either side, matching the
  existing workspace-package rule.
- Library modules may import each other (`text` imports `list`; the Marvel
  modules import `secure` and `text`), never project files.
- Importing the library grants no authority. Library functions are ordinary
  Koschei code: they hold no capability, and `ks caps` of a program that only
  uses the library stays empty.

## Verification

`tests/test_core_library_v1.py` runs every `text` and `list` function through
the real `ks run` path against a Python reference implementation;
`tests/test_secure_library_v1.py` pins `sha3_256` to NIST answers, `hashlib`
and its byte bound; `tests/test_marvel_library_v1.py` compares the Marvel
modules with their Python guardians. Each case embeds the
expected answer in a generated Koschei program, with seeded random inputs over
an alphabet chosen to force overlapping patterns, line breaks, blanks, escapes
and non-ASCII text. Resolution, shadowing, capability and lock behavior are
covered by the same file.

## Builds

`ks build` compiles library programs through the
[MIR-Go conformance adapter v2](MIR_GO_CONFORMANCE_ADAPTER_V2.md). The same
`.ks` library source is compiled; there is no second implementation, and
`tests/test_mir_go_native_v2_parity.py` checks that the binary prints exactly
what `ks run` prints. Per the native execution boundary this is a Go host
projection, not a Koschei-native runtime.

## What v1 does not claim

- **Catalog promotion.** `koschei/stdlib_catalog.py` describes host builtins and
  requires interpreter/native parity for `supported`. Core Library functions are
  module functions (`text.starts_with(value, prefix)`), not `String` methods, and
  are not counted there. The exception is `secure.hash`, which the catalog's
  `secure` family has always named; it is `supported` with its input bound
  enforced.
- **Locked builds.** Module Lock v1 covers project-local files only, so
  `ks lock create` rejects graphs that import the library with an explicit
  `KS1902` reason instead of a misleading path-escape message.
- **Workspaces.** The workspace resolver is unchanged; workspace members cannot
  import the library yet.
- **Bytes.** There is no byte type yet; digests travel as hex text.
- **Missing language features.** Generic `==` on type parameters and
  function-typed parameters are not available to user code, so operations such
  as `index_of` or a generic `fold` are deferred. Character-level operations
  (`slice` of text, case mapping) need a new kernel primitive and are deferred
  too.
