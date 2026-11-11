# Native Conduit IR v1

This slice migrates Koschei reusable `conduit` composition onto Native IR.

A conduit remains a local sealed aperture. It is not a function parameter, import, module lookup, runtime symbol table entry, or host callback.

The admission contract requires the provided slot set to exactly equal the canonical conduit slot set. Each authenticated slot value becomes a native literal atom before IR execution. No legacy `Program`, function declaration, local binding, return statement, or infix compatibility AST is constructed on this path.

The first composition gate proves reusable Whole inputs `40` and `2` resolve to `42`, then the root consumes that value through its own sealed conduit and resolves `42` again. Mixed `truth` and `glyphs` inputs are also admitted without coercion.

This is still a migration slice. Object Space graph decoding and Cell Reality projection continue to exist above this direct IR path and are the next migration targets.
