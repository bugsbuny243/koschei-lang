"""Conservative scope gate for native MIR execution.

MIR v3 does not yet encode general lexical scope enter/leave operations. Until
that is explicit, native execution must reject graphs where a source-visible
binding name is introduced more than once in a function or shadows a parameter.

Compiler-generated ``$mir_`` names are different: the parser cannot author that
reserved prefix and the MIR lowerer allocates each internal slot uniquely. A
single internal join/result slot may therefore be bound on mutually-exclusive
CFG branches and loaded after the join without becoming source-language
shadowing authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from .mir import MirGraph
from .mir_ir import MirBind


_COMPILER_INTERNAL_PREFIX = "$mir_"


@dataclass(frozen=True, slots=True)
class MirScopeSafety:
    safe: bool
    reasons: tuple[str, ...]


def _is_compiler_internal_binding(name: str) -> bool:
    return name.startswith(_COMPILER_INTERNAL_PREFIX)


def inspect_mir_scope_safety(mir: MirGraph) -> MirScopeSafety:
    mir.assert_sealed()
    reasons: list[str] = []
    for function in mir.root_module.functions:
        names = {parameter.name for parameter in function.parameters}
        for block in function.blocks:
            for instruction in block.instructions:
                if not isinstance(instruction, MirBind):
                    continue
                if instruction.name in names:
                    if _is_compiler_internal_binding(instruction.name):
                        # Rebinding one allocator-owned join/result slot on
                        # mutually-exclusive paths is not lexical shadowing.
                        continue
                    reasons.append(
                        f"{function.name}: repeated or shadowed binding "
                        f"{instruction.name!r} requires lexical-scope MIR"
                    )
                else:
                    names.add(instruction.name)
    return MirScopeSafety(not reasons, tuple(dict.fromkeys(reasons)))
