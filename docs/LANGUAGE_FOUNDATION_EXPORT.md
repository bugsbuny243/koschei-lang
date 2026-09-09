# Koschei Language Foundation Corpus v1

Koschei Lang owns the authoritative export boundary for language-foundation material used by optional downstream model training and evaluation. No external Koschei project is required for this corpus to exist, verify or remain useful.

## What v1 exports

`ks foundation-export build` collects only Git-tracked language material:

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

Trusted export requires the supplied commit to equal the checked-out Git `HEAD`. The exporter rejects dirty or untracked foundation paths and enumerates candidates through Git's tracked-file index, so ignored or untracked files cannot silently enter a corpus attributed to the commit.

Verify an existing artifact with:

```bash
ks foundation-export verify build/koschei-language-foundation.json
```

Verification rejects malformed UTF-8, ambiguous duplicate JSON object members, empty corpora, unsafe paths, hash/ID mismatches and family mismatches. The output file is no-replace; a pre-existing artifact is never silently overwritten.

## Leakage boundary

Documents are assigned a `family` before they leave this repository. All `.ks` files inside one example directory belong to the same family. For example:

```text
examples/supply_chain/main.ks
examples/supply_chain/analytics.ks
```

both belong to `example:supply_chain`.

All `.ks` files directly under `examples/` belong to `example:top-level`. This deliberately keeps adjacent imported modules such as `examples/app.ks` and `examples/risk.ks` together instead of risking train/evaluation leakage.

Translated reference variants also share a family: `README.md` and `README.tr.md` are both `reference:README`, while `.en.md` and `.tr.md` documentation variants normalize to the same base Markdown family.

A downstream dataset builder must keep a family entirely inside one of train, validation or test. This prevents a multi-file program or translated near-duplicate from teaching the model in train and then appearing as evaluation material.

## Trust boundary

The trusted build path proves which exported bytes came from the clean checked-out Koschei Lang commit and emits a canonical corpus SHA-256 for downstream pinning. The digest is not a digital signature; a downstream consumer must obtain the expected commit and corpus digest through its trusted handoff rather than trusting values copied from an untrusted artifact.

The corpus does not claim that every sentence in documentation is a formal language specification, that every example is production-safe, or that a model trained on the corpus understands Koschei. Those are separate validation gates.

Koschei Sentinel is reactivated, but it is still not a consumer dependency or trust root for this exporter. Any Sentinel handoff must use an explicit, versioned Koschei Fabric adapter and must not change the authoritative Lang corpus semantics, hashes, family boundaries, or trusted-export rules. The Lang exporter remains independently buildable and verifiable when Sentinel and Koschei Web3 are unavailable.
