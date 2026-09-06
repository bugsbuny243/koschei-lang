# KOSCHEI MIR OR RETURN NORMALIZATION V1

Status: dependency note only; implementation belongs on a separate core branch.

Agentic delegation work must not be layered on AST-derived capability authority. `OrReturnExpression` currently hides nested capability calls behind `MirAstFallback`, forcing `CompilerCapabilityEffectBasisV1` to retain a checked AST/Typed-HIR compatibility derivation.

Required invariant before delegation authority becomes canonical:

`effectful fallible call -> normalized MIR callsite -> single evaluation -> explicit success/failure control flow -> exact early return`

The implementation must preserve these laws:

- the fallible expression is evaluated exactly once;
- a nested capability call remains an ordinary normalized `MirMember -> MirCall` relation;
- success extracts only the success payload and continues;
- failure returns the original failure value unless an explicit replacement error is present;
- a replacement error is evaluated only on the failure path;
- capability identity is not reconstructed from AST for this construct;
- MIR fingerprinting/sealing covers the new normalized facts;
- no claim is made that runtime consumes MIR until the MIR execution boundary is actually implemented and tested.

This note creates no new syntax or authority system.