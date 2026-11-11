# Native Decision IR v1

This slice moves Koschei `settle` decision reality onto the Koschei-native IR path.

The admitted source remains a closed witness graph. `settle` is a graph equation over one truth condition and two same-domain candidate realities. It is not lowered to `if`, `else`, `match`, branch statements, function bodies, local variables, or return statements.

The Native IR contains only witness identities, native operations, native atoms, and the resolved witness identity. Execution realizes the selected candidate directly from Native IR.

Structural validity of both candidates remains enforced by the decision frontend before lowering. The active Native IR contains only the selected dependency reality plus the condition path.

This is migration work, not a new surface feature. Its purpose is to remove the legacy compatibility AST from the canonical execution definition of Koschei-native decision semantics.
