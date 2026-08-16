# Native Sealed Collection Reality v1

## Purpose

This slice introduces a bounded Koschei-native collection reality without copying conventional array/list semantics into the language core.

V1 deliberately provides no source-level or runtime contract for:

- `[]` indexing;
- numeric random access;
- append / pop / insert;
- mutable length;
- iterator escape;
- arbitrary callbacks;
- host-container identity;
- implicit element coercion.

A collection is an authenticated, bounded reality with one sealed scalar domain and a fixed cardinality/resource envelope.

## Sealed contract

The descriptor authenticates:

- project identity;
- collection identity;
- exact scalar domain: `whole`, `truth`, or `glyphs`;
- minimum and maximum item count;
- issue / expiry epochs;
- Whole absolute-value ceiling;
- Glyphs per-item byte ceiling;
- total admitted byte ceiling;
- zero authority;
- zero effects.

The canonical descriptor is authenticated with domain-separated HMAC-SHA256.

## Admission

Admission consumes a bounded item stream and materializes one opaque `NativeCollectionRealityV1`.

Every item must already inhabit the sealed native domain. V1 performs no conversion:

- `"40"` is not Whole `40`;
- `1` is not Truth `yes`;
- arbitrary objects are not Glyphs.

Text and mappings are explicitly rejected as ambient host containers rather than interpreted as collections.

## Opaque identity and integrity

A successful collection reality exposes:

- collection identity;
- sealed domain;
- count;
- deterministic digest.

The internal values are not given a public indexing API. The digest is domain-separated and binds collection identity, item domain, item length and canonical item payload in order.

## Closed projections

V1 allows only a small, domain-checked projection set:

- every domain: `count -> whole`;
- Whole collection: `sum -> whole`;
- Truth collection: `all -> truth`;
- Truth collection: `any -> truth`;
- Glyphs collection: `merge -> glyphs`.

A projection for the wrong domain fails closed. Whole sum also fails if aggregation would escape native Int64 range.

These projections are intentionally closed operations rather than general iteration or callback execution.

## Security properties

V1 rejects:

- stale / not-yet-valid contracts;
- descriptor tampering;
- wrong authentication keys;
- authority/effect inflation;
- cardinality overflow/underflow;
- scalar coercion;
- Whole item budget overflow;
- Glyphs item / total byte overflow;
- non-NFC or control-bearing Glyphs;
- wrong-domain projections;
- ambient string/mapping container admission.

## Relationship to #208

#208 established exact nested JSON tree admission. A future composition slice can admit a sealed nested external collection into this reality and then expose only closed aggregate projections to reusable Koschei logic.

The intended direction is:

`untrusted external collection -> exact sealed admission -> opaque native collection reality -> closed projection -> anonymous reusable conduit`

not:

`external array -> index/iterator/callback authority inside Koschei source`.

## Deliberate non-claims

V1 does not yet provide nested Cell collections, mixed-domain rows, keyed collections, sorting, filtering, mapping, streaming pagination, persistent collections, database rowsets, external JSON-array admission, or effect-bearing traversal. Those remain separate slices so the opaque/bounded invariant is not weakened accidentally.
