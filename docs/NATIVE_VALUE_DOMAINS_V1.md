# Koschei Native Value Domains v1

Status: experimental native-language slice stacked on sealed native relationships.

This slice expands the closed witness graph beyond Int64 without adding type declarations,
structs, enums, classes, implicit casts, or host-language literal syntax.

A witness resolves to one canonical value domain determined by the term that produced it:

- `whole` — signed Int64 mathematical reality;
- `truth` — canonical `yes` / `no` data reality, not control flow;
- `glyphs` — NFC-normalized UTF-8 human text with an exact byte-length admission contract.

Examples:

```text
witness amount 40
witness fee 2
witness total sum amount fee
resolve total
```

```text
witness enabled truth yes
resolve enabled
```

```text
witness label glyphs 5 café
witness doubled merge label label
resolve doubled
```

The graph remains source-order independent. Forward references are valid, execution order is
derived from dependencies, dormant witnesses fail closed, and exactly one `resolve` root is
observable. v1 admits at most 4096 witnesses per object and uses an explicit non-recursive
dependency walk so the host Python recursion limit cannot become an accidental language limit.

## Domain operations

- `sum`, `difference`, `product` require whole/whole;
- `merge` requires glyphs/glyphs and enforces the resulting UTF-8 byte budget;
- `same` requires identical domains and returns truth;
- there is no implicit numeric/text/truth coercion.

A domain mismatch is a native frontend error before compatibility-backend lowering. The
backend's Int/Bool/String nodes are internal ABI only; they are not the native source model.

## Glyph canonicality

Glyph values are admitted as:

```text
witness <name> glyphs <utf8-byte-count> <payload>
```

The whole source and payload must be Unicode NFC. The declared byte count must exactly equal
the UTF-8 payload byte count. Leading-zero byte-count aliases are rejected. NUL, C0/C1
controls, CR, tabs, malformed UTF-8, noncanonical lengths and over-budget values fail closed.

Bidirectional formatting/override controls that can visually reorder reviewed source are also
rejected. v1 explicitly rejects U+061C, U+200E/U+200F, U+202A..U+202E and U+2066..U+2069.
This is a source-integrity rule, not a claim that every Unicode spoofing problem is solved.

Every derived glyph `merge` is normalized to NFC *after* concatenation. This matters because
two individually canonical operands can form a decomposed sequence at their boundary. The
result budget is then measured on the canonical UTF-8 bytes.

Budgets:

- one glyph literal: at most 64 KiB UTF-8;
- one derived glyph value: at most 1 MiB UTF-8;
- native value source object: at most 1 MiB.

v1 intentionally does not claim arbitrary binary/string coverage. It is a bounded canonical
human-text domain. Arbitrary bytes and richer text transport require separate value domains
rather than weakening glyph canonicality.

## Closed-graph backend contract

The native value graph is closed: all witnesses, dependencies, domain checks, Int64 overflow
checks, glyph normalization and byte budgets are resolved before compatibility lowering.
Therefore the compatibility backend does **not** re-execute native `sum`, `same` or `merge`
semantics with host-style operators.

Instead, each checked witness is materialized as its already-proven canonical value below the
frontend boundary. Dependency order and witness identities are preserved for compiler/MIR
diagnostics, but the compatibility AST receives canonical literals. This prevents a backend
from turning a canonical `é` back into the decomposed `e + combining-acute` representation or
otherwise changing a checked native value.

Constant materialization is valid only for this closed, pure v1 graph. It is not a general rule
that future effectful or runtime-dependent Koschei expressions may be precomputed.

Executed parity gates require the frontend result and compatibility interpreter to agree for
`whole`, `truth` and `glyphs`, including NFC boundary composition. Public Object Space `run`
keeps its established process-style contract: successful execution returns status 0; tests
inspect the admitted sealed MIR separately when asserting the actual program value.

## Authenticated frontend identity

Native value domains use their own sealed Object Space graph schema and 32-byte frontend
identity. A project is parsed by this frontend only when sealed k0 graph metadata identifies
it. Source prefix, extension, filename, or parser success never selects this frontend.

The sealed metadata binds project identity, root object identity, the exact source artifact
digest and the exact value-domain frontend identity. Digest/frontend tampering and schema
downgrade attempts fail before interpreter execution. Public run/MIR/capability/native-source
views are also tested not to disclose project id, object id or physical locator identity.

v1 is one authoritative object. Typed multi-object relationship transport is a later contract;
existing Int64 relationship v1 is not silently widened to carry `truth` or `glyphs`.

## Executed scale and adversarial boundary

Targeted Railway gates exercise:

- full 4096-witness whole dependency chains;
- full 4096-witness glyph merge graphs;
- exact 1 MiB derived-glyph admission and the next doubling rejected;
- 4097th witness rejection;
- NFC alias and operand-boundary normalization attacks;
- bidi-control source attacks;
- cross-domain coercion attempts;
- sealed frontend/digest tampering and schema downgrade;
- frontend-to-backend value parity.

These are targeted slice gates, not a repository-wide production-readiness claim. GitHub-hosted
Actions must still execute normally before this stack can be treated as merge-ready.