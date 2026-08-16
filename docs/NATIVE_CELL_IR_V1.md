# Native Cell IR v1

This slice moves the post-validation Cell Reality projection path onto Koschei Native IR.

The authenticated Cell Projection frontend still proves the complete sealed schema before selection. Native IR accepts only an already-proven `NativeCellProjectionCheckV1`; it does not accept a loose raw scalar plus ordinal pair.

The selected scalar is carried as a Native IR atom. No `Program`, function declaration, local binding, return statement, member access, bracket index, tuple projection, or compatibility AST carrier is created on this path.

A proven cell scalar can also feed a reusable `conduit` slot directly. The source sees only its local sealed conduit slot; the authenticated cell ordinal remains projection metadata and never becomes source-level member/index authority.

V1 intentionally does not replace the existing authenticated full-schema validation. It replaces only the execution carrier after that proof.
