"""Normalized MIR contract for Koschei's fallible ``or return`` path.

The parser already models ``value or return [replacement]`` explicitly, but the
core MIR lowerer previously emitted an AST fallback for the whole expression.
That prevented otherwise normalized service code from entering the AST-free
direct MIR executor.

This slice lowers Error-union propagation to explicit MIR control flow. Option
and Result remain outside direct-MIR v1 because enum execution itself is still a
separate unsupported surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import mir_ir as _ir
from . import mir_native_runtime as _runtime
from .ast_nodes import OrReturnExpression, SourceLocation
from .type_system import BOOL, TypeNode

_INSTALLED = False
_ORIGINAL_LOWER_EXPRESSION = None
_ORIGINAL_INSPECT_SUPPORT = None
_ORIGINAL_EXECUTE_INSTRUCTION = None


@dataclass(frozen=True, slots=True)
class MirFallibleIsSuccess:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirFallibleUnwrap:
    target: int
    source: int
    type: TypeNode
    location: SourceLocation


def _lower_or_return(lowerer, expression: OrReturnExpression) -> int:
    value = lowerer._lower_expression(expression.value)

    condition = lowerer._new_value()
    lowerer._emit(
        MirFallibleIsSuccess(
            condition,
            value,
            BOOL,
            expression.location,
        )
    )

    success_block = lowerer._new_block()
    failure_block = lowerer._new_block()
    join_block = lowerer._new_block()
    lowerer._terminate(_ir.MirBranch(condition, success_block, failure_block))

    lowerer.current = failure_block
    replacement = (
        value
        if expression.error is None
        else lowerer._lower_expression(expression.error)
    )
    lowerer._terminate(_ir.MirReturn(replacement))

    lowerer.current = success_block
    target = lowerer._new_value()
    lowerer._emit(
        MirFallibleUnwrap(
            target,
            value,
            lowerer._type_of(expression),
            expression.location,
        )
    )
    lowerer._terminate(_ir.MirJump(join_block))

    lowerer.current = join_block
    return target


def _lower_expression(self, expression):
    if isinstance(expression, OrReturnExpression):
        return _lower_or_return(self, expression)
    return _ORIGINAL_LOWER_EXPRESSION(self, expression)


def _inspect_support(mir):
    report = _ORIGINAL_INSPECT_SUPPORT(mir)
    ignored = (
        "unsupported MIR instruction MirFallibleIsSuccess",
        "unsupported MIR instruction MirFallibleUnwrap",
    )
    reasons = tuple(
        reason
        for reason in report.reasons
        if not any(marker in reason for marker in ignored)
    )
    return _runtime.MirNativeSupport(not reasons, reasons)


def _execute_instruction(
    self,
    instruction,
    values,
    environment,
    mutable,
    module_key,
):
    if isinstance(instruction, MirFallibleIsSuccess):
        value = self._value(values, instruction.source)
        values[instruction.target] = not isinstance(value, _runtime._ErrorValue)
        return

    if isinstance(instruction, MirFallibleUnwrap):
        value = self._value(values, instruction.source)
        if isinstance(value, _runtime._ErrorValue):
            raise _runtime.MirNativeRuntimeError(
                "fallible MIR unwrap reached an Error on its success edge"
            )
        values[instruction.target] = value
        return

    return _ORIGINAL_EXECUTE_INSTRUCTION(
        self,
        instruction,
        values,
        environment,
        mutable,
        module_key,
    )


def install_fallible_mir_v1() -> None:
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
