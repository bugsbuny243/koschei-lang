# Koschei Native Semantic Kernel v1

Status: **experimental language foundation; stacked on Object Space v1**

This slice begins the source-language migration away from the legacy mainstream-shaped grammar. It is intentionally small. Its purpose is to establish a semantic family that is not `fn/let/return/import/{...}` with renamed words.

## The semantic unit is an object reality, not a file full of functions

A native v1 source object is one closed immutable value graph:

```text
witness base 40
witness fee 2
witness total sum base fee
witness doubled product total 2
resolve doubled
```

The root Object Space identity selects which object is authoritative. There is no native `main` declaration or semantic entry filename.

### `witness` is not `let`

A witness is a named node/equation in a dependency graph.

- it is immutable;
- it is defined exactly once;
- it may refer to a witness written later in the source;
- source line order has no execution meaning;
- the compiler derives dependency order from the graph;
- every admitted witness must be reachable from the resolved root.

Therefore this is valid and has the same meaning as the example above:

```text
witness doubled product total 2
witness total sum base fee
witness fee 2
resolve doubled
witness base 40
```

A sequential variable language could not generally make that guarantee merely by renaming `let`.

### `resolve` is not `return`

A native object has exactly one resolve clause. It selects the one observable value of the closed witness graph.

`resolve` cannot appear conditionally or exit early. It is a graph-root invariant. Any witness not contributing to it is rejected as dormant reality rather than silently admitted as dead/hidden code.

## V1 mathematical relations

V1 intentionally keeps arithmetic tiny:

```text
witness a 9
witness b 4
witness x sum a b
witness y difference a b
witness z product x y
resolve z
```

`sum`, `difference`, and `product` are general mathematical relations represented as prefix graph vocabulary. They are not replacements for a borrowed infix grammar. V1 has no native punctuation operators.

All values are signed Int64. Literal or computed overflow fails closed.

## Canonical text contract

Native kernel v1 deliberately has a narrow canonical spelling:

- ASCII only;
- LF newlines only;
- exactly one final LF;
- no blank clauses;
- no tabs or indentation;
- exactly one ASCII space between tokens;
- witness identities use lowercase ASCII letters/digits, start with a letter, and are at most 64 bytes;
- legacy punctuation and legacy grammar words are rejected rather than passed to the compatibility parser.

The ASCII-only v1 restriction is a security/canonicalization choice, not a permanent statement that Koschei can never support international developer labels. A later display-label layer may be Unicode while canonical executable identity remains confusable-resistant.

## Closed-graph admission

Before execution/lowering the kernel rejects:

- duplicate witness identity;
- missing or duplicate resolve;
- unknown dependency;
- dependency cycle;
- dormant witness outside the resolved graph;
- malformed operation arity;
- noncanonical whitespace/newlines;
- Unicode confusable/normalization aliases;
- legacy grammar/punctuation fallback;
- Int64 overflow.

The no-dormant-witness rule is deliberate: an admitted native object should not carry executable-looking nodes that are outside its declared reality.

## Compatibility lowering is not source semantics

The current compiler backend still understands the legacy AST/MIR. Native v1 therefore lowers the admitted witness graph into an internal pure function body in **dependency order**.

That internal representation may contain legacy nodes such as immutable bindings, binary operations, and an internal `main` ABI name. Those names are below the native frontend and are not programmer-visible grammar, project layout, or authority.

The migration rule is:

> Native semantics define the program; compatibility IR is allowed to encode those semantics temporarily, but compatibility IR must never define or constrain the native surface.

This slice also sends the lowered form through the existing semantic checker so the new frontend begins reusing the mature typed/runtime path without pretending the old grammar is native.

## Originality contract

Native surface words are separately registered with explicit provenance:

- `witness` — immutable dependency reality, not sequential variable declaration;
- `resolve` — single observable graph root, not early control flow;
- `sum`, `difference`, `product` — general mathematical relations without borrowed operator grammar.

The project originality gate still keeps the old keywords and punctuation as migration debt. V1 does not retire them globally yet because the legacy compatibility frontend remains supported.

## Non-claims

This is the first semantic kernel slice, not a complete programming language.

V1 does **not yet** provide:

- native multi-object relationship syntax;
- native authority/effect declarations;
- native data structures or nominal types;
- branching/recursion/iteration semantics;
- async/concurrency;
- persistence/network/database APIs;
- direct native MIR independent of compatibility lowering;
- automatic Object Space frontend selection.

Those must be added as Koschei-native semantic concepts, one tested/red-teamed slice at a time.

## Next slice after this gate passes

1. bind Object Space graph metadata to an explicit native-frontend identity so no source magic string or extension selects grammar;
2. parse native objects directly from the sealed Object Space graph with no legacy-parser fallback;
3. introduce native **relationship slots** between object identities without `import`/filename semantics;
4. then introduce authority/effect contracts as graph constraints, not function-parameter decoration.
