# Koschei Lang product direction — 2026-09-10

Koschei Lang is an independent, general-purpose programming language built around
cybersecurity. It owns its semantics, compiler, standard library, runtime, identity,
authority, verification and developer ecosystem. The ambition is a world-leading
language with its own libraries and no required external language/package runtime
in the completed product.

Rust is the primary competitive reference. The owner's 100x-security ambition is
a development target. A claim of achieved superiority requires defined threat
models, metrics and comparable executed tests. Existing bootstrap Python and native
Go implementation paths remain preserved; complete self-hosted independence is not
claimed by this change.

Web3 integration and agent policy are applications of Lang. They do not narrow its
language scope. The original main vision and existing compiler, library, runtime,
Matrix and release-trust work remain authoritative in their respective domains.

## Lang + Sentinel commercial packages

Every commercial package contains both Lang and Sentinel. They retain independent
implementations and release gates; buying both does not make the model a compiler
dependency or give model output language/runtime authority. No prices or tier
limits are introduced here.

`ks-bundle-check manifest.json --artifacts-dir ./artifacts` checks the same bundle
contract used by `sentinel-bundle-check`. Without `--artifacts-dir` it validates
metadata only. Source-only use is available as
`python koschei/commercial_bundle_v1.py manifest.json`.

See [the bundle contract](COMMERCIAL_BUNDLE_V1.md) and
`fabric/product-direction.v1.json`. This is a packaging integrity slice, not a
native-runtime promotion or a completed dependency-independence claim.
