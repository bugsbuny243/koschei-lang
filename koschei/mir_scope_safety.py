"""Conservative scope gate for native MIR execution.

MIR v3 does not yet encode lexical scope enter/leave operations. Until that is
explicit, native execution must not accept a graph where the same source binding
name is introduced more than once in a function or shadows a parameter. The AST
compatibility interpreter remains the semantic reference for those programs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .mir import MirGraph
from .mir_ir import MirBind


@dataclass(frozen=True, slots=True)
class MirScopeSafety:
    safe: bool
    reasons: tuple[str, ...]


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
                    reasons.append(
                        f"{function.name}: repeated or shadowed binding "
                        f"{instruction.name!r} requires lexical-scope MIR"
                    )
                else:
                    names.add(instruction.name)
    return MirScopeSafety(not reasons, tuple(dict.fromkeys(reasons)))
