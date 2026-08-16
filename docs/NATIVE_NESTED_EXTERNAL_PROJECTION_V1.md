# Native Nested External Projection v1

This slice extends the sealed typed external boundary with an exact nested JSON projection contract.

The security rule is simple: a nested payload is not trusted because only some leaves are later used. The complete admitted tree shape must match the sealed projection exactly.

## Contract

A projection seals:

- project identity;
- boundary identity;
- ordered anonymous native output slots;
- exact external path for each slot;
- exact `whole`, `truth`, or `glyphs` domain for each leaf;
- Whole and Glyphs resource ceilings;
- maximum payload bytes;
- issue and expiry Object Space epochs;
- zero authority and zero effects.

The canonical contract is authenticated with a domain-separated HMAC-SHA256 tag.

## External names do not become Koschei authority

A sealed path such as:

`profile -> display -> label`

exists only in authenticated boundary metadata. Successful admission returns only the boundary identity and ordered `NativeValue` slots. It does not return external paths and does not synthesize witness names, member access, namespaces, imports, call targets, or dynamic selectors.

The intended path remains:

`untrusted nested payload -> sealed exact projection -> anonymous native slots -> reusable conduit`

## Exact-shape admission

V1 rejects the complete payload when any of the following occurs:

- an unknown top-level key exists;
- an unknown nested sibling exists;
- a sealed leaf is missing;
- a mapping appears where a scalar leaf was sealed;
- a scalar appears where a branch was sealed;
- the payload exceeds the sealed byte ceiling;
- a path exceeds the v1 depth ceiling;
- scalar domain or scalar resource checks fail;
- the contract is stale or not yet valid;
- the canonical contract or authentication tag is modified;
- the authentication key is wrong.

Unknown fields are not silently ignored.

## Prefix ambiguity gate

A contract cannot seal one path as a leaf while simultaneously using it as a parent branch. For example, sealing both `profile` and `profile -> name` is rejected at contract creation.

## V1 limits

- JSON-compatible mappings only;
- maximum depth: 8;
- maximum sealed leaves: 64;
- maximum path segment: 128 UTF-8 bytes;
- maximum total payload: 1 MiB;
- no arrays;
- no wildcard paths;
- no optional leaves;
- no implicit coercion;
- no effects or authority.

Arrays, optional/union shapes, HTTP body decoding, and DB rowset admission belong in later slices rather than weakening this exact-tree boundary.
