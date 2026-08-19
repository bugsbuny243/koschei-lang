# Koschei Library Nucleus v0

Koschei Lang is not the starting point. The library is.

The public package must not contain the full semantic corpus, private defense
knowledge, internal composition maps, or runtime decision material. A client
receives only small opaque root handles and verifiable commitments. The private
library core retains the large corpus and binds it to those handles.

## Non-copy rule

This nucleus is not a wrapper around React, Node, npm, HTML, CSS, JavaScript,
Python, Go, Rust, or another language/framework execution model. If removing
Koschei names reveals one of those systems underneath, the design is rejected.

## Four planes

1. Public root plane
   - tiny root identity
   - generation
   - semantic commitment
   - policy commitment
   - composition commitment
   - no corpus, no internal map, no authority

2. Private corpus plane
   - long-form meanings
   - positive and negative cases
   - invariants
   - adversarial cases
   - composition knowledge
   - histories and scenario knowledge
   - never shipped as distributable package content

3. Activation plane
   - a root is activated only for a bound execution context
   - activation is nonce-bound and keyed
   - a public handle alone cannot reproduce private semantics

4. Execution plane
   - future Koschei Lang syntax requests roots
   - the runtime evaluates private semantics and returns bounded results/evidence
   - client syntax remains small while the hidden core may be very large

## First invariant

Small visible code must never imply small internal semantics.

## Security invariant

Hidden data is an additional barrier, not the sole security boundary. Exposure
of a public handle or commitment must not grant private corpus access or runtime
authority.

## Initial root names

`ka`, `vor`, `shi`, `thal`, `nur`, and any later roots are placeholders until
their private corpus is designed. They are not aliases for existing programming
keywords.

## Next build step

Create the private corpus schema itself: not the corpus contents yet, but the
format for long-form meaning, invariants, counterexamples, attack scenarios,
compositions, version lineage, and evidence binding. Only after that schema is
stable do we begin authoring the first real root corpus.
