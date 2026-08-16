# Native External Boundary v1

## Purpose

Native External Boundary v1 converts untrusted JSON-, HTTP-, or database-shaped mappings into sealed Koschei native scalar values without exposing ambient external names to Koschei source.

The boundary is intentionally not a network client, web framework, JSON parser, ORM, or database driver. Those systems remain outside the language authority model. The boundary accepts their already-decoded mapping and decides whether it is admissible.

## Authority model

A boundary contract seals and authenticates:

- project identity;
- boundary identity;
- exact external source kind (`json`, `http`, or `db`);
- exact external field set;
- anonymous contiguous output slots;
- exact native domain for every slot (`whole`, `truth`, `glyphs`);
- Whole absolute-value ceilings;
- Glyphs byte ceilings;
- whole-payload byte ceiling;
- issue and expiry Object Space epochs;
- zero-authority and zero-effect ceilings.

The canonical contract is authenticated with HMAC-SHA256 under a 32..64 byte boundary key and a domain-separated Koschei v1 context.

## No ambient field authority

External names such as:

- `amount`;
- `display.label`;
- an HTTP parameter name;
- a database column name;

exist only inside authenticated boundary metadata and the untrusted input mapping.

A successful admission returns only:

- the boundary identity;
- an ordered tuple of native `NativeValue` slots.

External field names are not returned and do not become Koschei witness identities, member names, source paths, namespace names, or call targets.

## Strict admission

V1 is fail-closed:

- payload keys must exactly equal the sealed field set;
- source kind must exactly equal the sealed source kind;
- current epoch must be inside the sealed validity window;
- `whole` accepts Python integers only and explicitly rejects booleans and text coercion;
- `truth` accepts booleans only;
- `glyphs` accepts Unicode NFC text only, rejects control characters, and enforces the sealed UTF-8 byte ceiling;
- payload serialization must remain inside the sealed byte ceiling;
- unknown fields are rejected rather than ignored;
- contract or tag modification fails authentication;
- v1 admits zero authority and zero effects only.

## Mixed reusable composition

The admitted tuple can feed the mixed reusable materializer by slot. This creates the desired separation:

`external name -> sealed boundary rule -> anonymous native slot -> reusable conduit`

not:

`external name -> Koschei source authority`.

This means a JSON key, HTTP parameter, or DB column cannot silently become a source-level member/field/call surface.

## Deliberate non-claims

V1 does not yet:

- open sockets or make HTTP requests;
- parse raw HTTP framing;
- connect to databases;
- parse arbitrary nested JSON documents;
- authorize effects;
- perform implicit scalar conversion;
- admit optional or unknown fields;
- expose external field names to source code.

Those are separate future slices and must preserve the same sealed admission invariant.
