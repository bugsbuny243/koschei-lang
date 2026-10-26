"""Normalized direct-MIR support for Koschei interpolated strings."""

from __future__ import annotations

from dataclasses import dataclass

from . import mir_ir as _ir
from . import mir_native_runtime as _runtime
from .ast_nodes import InterpolatedString, SourceLocation
from .type_system import STRING, TypeNode

_INSTALLED = False
_ORIGINAL_LOWER_EXPRESSION = None
_ORIGINAL_INSPECT_SUPPORT = None
_ORIGINAL_EXECUTE_INSTRUCTION = None


@dataclass(frozen=True, slots=True)
class MirInterpolate:
    target: int
    items: tuple[int, ...]
    type: TypeNode
    location: SourceLocation


def _lower_expression(self, expression):
    if not isinstance(expression, InterpolatedString):
        return _ORIGINAL_LOWER_EXPRESSION(self, expression)

    items = tuple(self._lower_expression(part) for part in expression.parts)
    target = self._new_value()
    self._emit(MirInterpolate(target, items, STRING, expression.location))
    return target


def _inspect_support(mir):
    report = _ORIGINAL_INSPECT_SUPPORT(mir)
    marker = "unsupported MIR instruction MirInterpolate"
    reasons = tuple(reason for reason in report.reasons if marker not in reason)
    return _runtime.MirNativeSupport(not reasons, reasons)


def _execute_instruction(
    self,
    instruction,
    values,
    environment,
    mutable,
    module_key,
):
    if isinstance(instruction, MirInterpolate):
        values[instruction.target] = "".join(
            _runtime._to_string(self._value(values, item))
            for item in instruction.items
        )
        return
    return _ORIGINAL_EXECUTE_INSTRUCTION(
        self,
        instruction,
        values,
        environment,
        mutable,
        module_key,
    )


def install_interpolation_mir_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_LOWER_EXPRESSION, _ORIGINAL_INSPECT_SUPPORT
    global _ORIGINAL_EXECUTE_INSTRUCTION
    if _INSTALLED:
        return

    _ORIGINAL_LOWER_EXPRESSION = _ir._FunctionLowerer._lower_expression
    _ir._FunctionLowerer._lower_expression = _lower_expression

    _ORIGINAL_INSPECT_SUPPORT = _runtime.inspect_native_mir_support
    _runtime.inspect_native_mir_support = _inspect_support

    _ORIGINAL_EXECUTE_INSTRUCTION = _runtime._MirExecutor._execute_instruction
    _runtime._MirExecutor._execute_instruction = _execute_instruction

    _INSTALLED = True
