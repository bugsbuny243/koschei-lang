"""Fail-closed import-shadow guard for direct MIR module member admission.

Direct MIR runtime resolution intentionally gives lexical bindings and local
functions precedence over imported module aliases. The support inspector must
make the same decision before execution; otherwise a shadowed import name could
be misclassified as an executable module member even though runtime would load
the local value instead.
"""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .mir_ir import MirBind, MirLoad, MirMember

_INSTALLED = False
_ORIGINAL_IS_DIRECT_MODULE_MEMBER = None


def _shadowed_names(module, function) -> set[str]:
    names = {parameter.name for parameter in function.parameters}
    names.update(candidate.name for candidate in module.functions)
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirBind):
                names.add(instruction.name)
    return names


def _is_direct_module_member(mir, module_key, function, instruction: MirMember) -> bool:
    module = mir.module_of(module_key)
    source = _mir._definitions(function).get(instruction.object)
    if not isinstance(source, MirLoad):
        return False

    # Runtime MirLoad resolution is environment -> local function -> import ->
    # builtin. Mirror that precedence conservatively in preflight admission.
    # We reject the entire function-name set and every normalized local binding,
    # even when a particular shadow is introduced after the member expression;
    # v1 prefers a false-negative over claiming AST-free support incorrectly.
    if source.name in _shadowed_names(module, function):
        return False

    return _ORIGINAL_IS_DIRECT_MODULE_MEMBER(
        mir, module_key, function, instruction
    )


def install_mir_native_module_shadow_guard_v1() -> None:
    global _INSTALLED, _ORIGINAL_IS_DIRECT_MODULE_MEMBER
    if _INSTALLED:
        return
    _ORIGINAL_IS_DIRECT_MODULE_MEMBER = _mir._is_direct_module_member
    _mir._is_direct_module_member = _is_direct_module_member
    _INSTALLED = True
