# Object Space Native IR Dispatch v1

This slice establishes the first execution-authority path from authenticated Object Space metadata directly to Koschei Native IR.

The routing rule is metadata-authoritative. Source bytes, filenames, extensions, parser success and visual resemblance never select the Native IR frontend.

V1 supports only the authenticated native witness frontend. Any other Object Space schema fails closed on this API until an explicit Native IR handler exists. There is no legacy fallback.

The path is:

`sealed Object Space frontend identity -> native witness graph admission -> Native IR -> native value`

It does not construct `Program`, `ModuleGraph`, `GenericFunctionDeclaration`, `LetStatement`, `ReturnStatement` or `BinaryExpression` as execution carriers.

Security gates cover frontend identity substitution, opened-payload digest substitution and attempts to route a native-looking source through an unsupported Object Space schema.

Compatibility command paths remain separate migration debt. This v1 does not claim every existing Object Space schema or compiler command has already moved to Native IR.
