# Koschei Lang product direction — updated 2026-10-05

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

## Standalone commercial product

Koschei Lang is sold and licensed separately from Koschei Sentinel and Koschei
Web3 Hub. Each product has its own entitlement, pricing, distribution and release
gates.

Lang may interoperate with Sentinel or Web3 through explicit SDKs, adapters and
versioned contracts. Such interoperability does not create a shared commercial
package and does not make either external product a compiler/runtime dependency.

The historical `koschei.commercial-bundle.v1` integrity tooling may remain for
compatibility and internal artifact verification, but it no longer defines the
commercial sales model.

See [the current standalone product charter](PRODUCT_CHARTER_LANG_V1.md) and
`fabric/product-direction.v1.json` for the authoritative product boundary.
