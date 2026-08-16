# Koschei Native IR Execution v1

This slice removes the first compatibility-AST dependency from the Koschei-native value path.

## Problem

The native source frontend introduced by #196 and widened by #199 has genuinely non-mainstream source semantics, but its backend bridge still materializes legacy compiler nodes such as `Program`, `GenericFunctionDeclaration`, `LetStatement`, `ReturnStatement`, and infix `BinaryExpression`.

That compatibility layer is implementation debt. It must not become the semantic definition of Koschei.

## Native IR

`NativeIrRealityV1` represents one closed witness reality directly.

It contains only:

- native witness identity;
- native operation identity;
- native literal/reference atoms;
- the resolved witness identity.

It has no function, parameter, statement, block, local variable, return statement, imported module, member access, brace grammar, or infix operator model.

## Execution

`execute_native_ir_v1()` realizes `whole`, `truth`, and `glyphs` values directly from native IR and enforces native domain and resource rules.

The current v1 operation set is the already-admitted native value vocabulary:

- `sum`
- `difference`
- `product`
- `same`
- `merge`

This does not add source syntax. It replaces one host-shaped backend dependency.

## Non-claims

This slice does not yet migrate `settle`, reusable `conduit`, Cell Reality composition, Object Space dispatch, native Go emission, or every public compiler command to Native IR.

Those are subsequent migration steps. The key ratchet is that new native language work should extend this IR path rather than reconstructing the legacy AST.
