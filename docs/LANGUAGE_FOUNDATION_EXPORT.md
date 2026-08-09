# Koschei Language Foundation Corpus v1

Koschei Sentinel must learn Koschei from repository truth before it is trained to teach or assist with the language. The language repository therefore owns the authoritative export boundary.

## What v1 exports

`ks foundation-export build` collects only checked-in language material:

- `README.md` and `README.tr.md` when present;
- Markdown files under `docs/`;
- Koschei `.ks` source files under `examples/`.

The result uses schema `koschei.language-foundation-corpus.v1`. Every document carries its path, kind, family, source SHA-256 and a content-derived document ID. The complete corpus is bound to an explicit 40-character source commit and a canonical corpus SHA-256.

This is source material, not synthetic instruction data. The exporter does not ask another model to invent answers about Koschei.

## Build

```bash
ks foundation-export build \
  --repo-root . \
  --source-commit <exact-koschei-lang-commit> \
  --output build/koschei-language-foundation.json
```

The source commit is required instead of being guessed from a mutable branch name.

Verify an existing artifact with:

```bash
ks foundation-export verify build/koschei-language-foundation.json
```

The output file is no-replace. A pre-existing artifact is never silently overwritten.

## Leakage boundary

Documents are assigned a `family` before they leave this repository. All `.ks` files inside one example directory belong to the same family. For example:

```text
examples/supply_chain/main.ks
examples/supply_chain/analytics.ks
```

both belong to `example:supply_chain`.

A downstream dataset builder must keep a family entirely inside one of train, validation or test. This prevents a multi-file program from teaching the model in train and then appearing as a near-duplicate benchmark in test.

Reference documents are independent families keyed by their repository path.

## Trust boundary

The corpus proves which bytes came from which Koschei language commit. It does not claim that every sentence in documentation is a formal language specification, that every example is production-safe, or that a model trained on the corpus understands Koschei. Those are separate validation gates.
