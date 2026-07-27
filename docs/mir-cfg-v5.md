# MIR v2 control-flow graph

Koschei lowers checked function bodies into explicit basic blocks before backend execution.

Implemented instructions include constants, loads, bindings, stores, unary and binary operations, member access, and calls. Blocks end with an explicit jump, branch, return, or unreachable terminator. `if` and `while` therefore have visible control-flow edges instead of being hidden inside backend-specific AST traversal.

Unsupported constructs remain visible as `ast_fallback`; they are not silently presented as normalized MIR. The next milestone removes those fallback nodes and makes the interpreter and native backend consume normalized instructions directly.

The repository includes `examples/mir_cfg_project.ks` as an executable project and verifies that the existing supply-chain attack remains rejected with `KS2401`.
