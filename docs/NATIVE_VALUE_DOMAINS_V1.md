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
observable.

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
the UTF-8 payload byte count. NUL, C0/C1 controls, CR, tabs, malformed UTF-8, noncanonical
lengths and over-budget values fail closed.

v1 intentionally does not claim arbitrary binary/string coverage. It is a bounded canonical
human-text domain. Arbitrary bytes and richer text transport require separate value domains
rather than weakening glyph canonicality.

## Authenticated frontend identity

Native value domains use their own sealed Object Space graph schema and 32-byte frontend
identity. A project is parsed by this frontend only when sealed k0 graph metadata identifies
it. Source prefix, extension, filename, or parser success never selects this frontend.

v1 is one authoritative object. Typed multi-object relationship transport is the next
contract; existing Int64 relationship v1 is not silently widened to carry new domains.
