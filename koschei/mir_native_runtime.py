"""Direct executor for Koschei's normalized MIR core.

This module is intentionally strict. It executes supported MIR instructions and
control-flow blocks directly; it never consults the source AST and never falls
back to the tree-walking interpreter. Unsupported constructs are rejected before
execution so backend progress is measurable instead of cosmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .interpreter import EnumValue
from .mir import MirFunction, MirGraph
from .mir_extension_instructions_v4 import (\n    MirStructFinish,\n    MirStructNew,\n    MirStructSet,\n    MirVariantIs,\n    MirVariantPayload,\n)
from .mir_ir import (
    MirAstFallback,
    MirBinary,
    MirBind,
    MirBranch,
    MirCall,
    MirConst,
    MirIterHasNext,
    MirIterInit,
    MirIterNext,
    MirJump,
    MirList,
    MirLoad,
    MirMember,
    MirReturn,
    MirStore,
    MirUnary,
    MirUnreachable,
)
from .mir_variant_runtime_v1 import (
    MirVariantRuntimeError,
    variant_is_v1,
    variant_payload_v1,
)

_SUPPORTED_BINARY = frozenset({"+", "-", "*", "==", "!=", "<", "<=", ">", ">="})
_SUPPORTED_UNARY = frozenset({"!", "-", "+"})
_BUILTINS = frozenset({"print", "println", "Error", "Some", "None", "Ok", "Err"})
_MAX_CALL_DEPTH = 512
_DEFAULT_MAX_STEPS = 1_000_000


class MirNativeUnsupported(ValueError):
    """Raised when a graph cannot yet be executed without AST compatibility."""


class MirNativeRuntimeError(RuntimeError):
    """Raised when a normalized MIR contract is violated during execution."""


class MirNativeStepBudgetExceeded(MirNativeRuntimeError):
    """Raised when direct MIR execution exhausts its global step budget."""


class MirNativeCallDepthExceeded(MirNativeRuntimeError):
    """Raised when direct MIR execution exhausts its call-frame budget."""


class MirNativeProgramError(MirNativeRuntimeError):
    """Raised when the Koschei program returns an Error value from main."""


@dataclass(frozen=True, slots=True)
class MirNativeSupport:
    supported: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FunctionRef:
    name: str
    module_key: str | None = None


@dataclass(frozen=True, slots=True)
class _ModuleRef:
    key: str


@dataclass(frozen=True, slots=True)
class _BuiltinRef:
    name: str


@dataclass(frozen=True, slots=True)
class _ErrorValue:
    message: str


@dataclass(slots=True)
class _ListIterator:
    items: tuple[Any, ...]
    index: int = 0


class _Unit:
    __slots__ = ()


_UNIT = _Unit()


def _definitions(function: MirFunction) -> dict[int, Any]:
    result: dict[int, Any] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            if isinstance(target, int):
                result[target] = instruction
    return result


def _is_direct_module_member(mir: MirGraph, module_key: str, function: MirFunction, instruction: MirMember) -> bool:
    module = mir.module_of(module_key)
    source = _definitions(function).get(instruction.object)
    if not isinstance(source, MirLoad):
        return False
    target_key = module.imports.get(source.name)
    if target_key is None or target_key not in mir.modules:
        return False
    target = mir.module_of(target_key)
    return any(candidate.name == instruction.member for candidate in target.functions)


def inspect_native_mir_support(mir: MirGraph) -> MirNativeSupport:
    """Return deterministic reasons why a graph is not native-MIR executable yet."""

    mir.assert_sealed()
    reasons: list[str] = []
    root = mir.root_module

    main = next((item for item in root.functions if item.name == "main"), None)
    if main is None:
        reasons.append("native MIR execution requires main")
    elif main.parameters:
        reasons.append("native MIR v1 requires zero-parameter main")

    supported_instructions = (
        MirConst,
        MirLoad,
        MirBind,
        MirStore,
        MirUnary,
        MirBinary,
        MirList,
        MirIterInit,
        MirIterHasNext,
        MirIterNext,
        MirMember,
        MirCall,
        MirVariantIs,
        MirVariantPayload,
    )
    for module in mir.in_dependency_order():
        if module.program.structs:
            reasons.append(f"{module.name}: native MIR v1 does not execute structs yet")
        if module.program.enums:
            reasons.append(f"{module.name}: native MIR v1 does not execute enums yet")
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    label = f"{module.name}.{function.name}"
                    if isinstance(instruction, MirAstFallback):
                        reasons.append(
                            f"{label}: AST fallback remains for {instruction.node_kind}"
                        )
                    elif isinstance(instruction, MirMember):
                        if not _is_direct_module_member(
                            mir, module.key, function, instruction
                        ):
                            reasons.append(
                                f"{label}: member access is not native-MIR yet"
                            )
                    elif (
                        isinstance(instruction, MirBinary)
                        and instruction.operator not in _SUPPORTED_BINARY
                    ):
                        reasons.append(
                            f"{label}: binary operator "
                            f"{instruction.operator!r} is not native-MIR yet"
                        )
                    elif (
                        isinstance(instruction, MirUnary)
                        and instruction.operator not in _SUPPORTED_UNARY
                    ):
                        reasons.append(
                            f"{label}: unary operator "
                            f"{instruction.operator!r} is not native-MIR yet"
                        )
                    elif not isinstance(instruction, supported_instructions):
                        reasons.append(
                            f"{label}: unsupported MIR instruction "
                            f"{type(instruction).__name__}"
                        )
    return MirNativeSupport(not reasons, tuple(dict.fromkeys(reasons)))


def run_mir_native(
    mir: MirGraph,
    *,
    max_steps: int = _DEFAULT_MAX_STEPS,
    max_call_depth: int = _MAX_CALL_DEPTH,
) -> int:
    """Execute a fully supported graph from MIR blocks only.

    No AST compatibility path exists here. Callers that need legacy compatibility
    must choose it explicitly outside this function.
    """

    support = inspect_native_mir_support(mir)
    if not support.supported:
        raise MirNativeUnsupported("; ".join(support.reasons))
    if max_steps <= 0:
        raise ValueError("max_steps must be a positive integer")
    if max_call_depth <= 0 or max_call_depth > _MAX_CALL_DEPTH:
        raise ValueError(f"max_call_depth must be between 1 and {_MAX_CALL_DEPTH}")
    executor = _MirExecutor(
        mir,
        max_steps=max_steps,
        max_call_depth=max_call_depth,
    )
    result = executor.execute_main()
    if isinstance(result, _ErrorValue):
        raise MirNativeProgramError(result.message)
    return 0


class _MirExecutor:
    def __init__(
        self,
        mir: MirGraph,
        *,
        max_steps: int,
        max_call_depth: int,
    ) -> None:
        self.mir = mir
        self.functions_by_module = {
            key: {item.name: item for item in module.functions}
            for key, module in mir.modules.items()
        }
        # Compatibility view for installed direct-MIR adapters. During a call it
        # is rebound to that function's own module namespace.
        self.functions = self.functions_by_module[mir.root]
        self.current_module_key = mir.root
        self.max_steps = max_steps
        self.max_call_depth = max_call_depth
        self.steps = 0
        self.depth = 0

    def execute_main(self) -> Any:
        main = self.functions_by_module[self.mir.root].get("main")
        if main is None:
            raise MirNativeRuntimeError("main function is missing")
        return self._call(main, [], self.mir.root)

    def _consume_step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise MirNativeStepBudgetExceeded(
                f"native MIR execution exceeded {self.max_steps} steps"
            )

    def _call(
        self,
        function: MirFunction,
        arguments: list[Any],
        module_key: str | None = None,
    ) -> Any:
        active_module_key = module_key or self.current_module_key
        module_functions = self.functions_by_module.get(active_module_key)
        if module_functions is None:
            raise MirNativeRuntimeError(
                f"call targets unknown MIR module {active_module_key!r}"
            )
        if len(arguments) != len(function.parameters):
            raise MirNativeRuntimeError(
                f"{function.name} expects {len(function.parameters)} arguments, "
                f"got {len(arguments)}"
            )
        if self.depth >= self.max_call_depth:
            raise MirNativeCallDepthExceeded(
                f"native MIR call depth exceeded {self.max_call_depth}"
            )

        environment: dict[str, Any] = {}
        mutable: set[str] = set()
        for parameter, value in zip(function.parameters, arguments, strict=True):
            environment[parameter.name] = value

        blocks = {block.id: block for block in function.blocks}
        values: dict[int, Any] = {}
        current = 0
        previous_functions = self.functions
        previous_module_key = self.current_module_key
        self.functions = module_functions
        self.current_module_key = active_module_key
        self.depth += 1
        try:
            while True:
                block = blocks.get(current)
                if block is None:
                    raise MirNativeRuntimeError(
                        f"{function.name} jumped to unknown block {current}"
                    )
                for instruction in block.instructions:
                    self._consume_step()
                    self._execute_instruction(
                        instruction,
                        values,
                        environment,
                        mutable,
                        active_module_key,
                    )

                self._consume_step()
                terminator = block.terminator
                if isinstance(terminator, MirReturn):
                    return (
                        _UNIT
                        if terminator.value is None
                        else self._value(values, terminator.value)
                    )
                if isinstance(terminator, MirJump):
                    current = terminator.target
                    continue
                if isinstance(terminator, MirBranch):
                    condition = self._value(values, terminator.condition)
                    if not isinstance(condition, bool):
                        raise MirNativeRuntimeError("MIR branch condition must be Bool")
                    current = terminator.then_block if condition else terminator.else_block
                    continue
                if isinstance(terminator, MirUnreachable):
                    raise MirNativeRuntimeError(
                        f"reached MIR unreachable block: {terminator.reason}"
                    )
                raise MirNativeRuntimeError(
                    f"unsupported MIR terminator {type(terminator).__name__}"
                )
        finally:
            self.depth -= 1
            self.functions = previous_functions
            self.current_module_key = previous_module_key

    def _execute_instruction(
        self,
        instruction: Any,
        values: dict[int, Any],
        environment: dict[str, Any],
        mutable: set[str],
        module_key: str,
    ) -> None:
        if isinstance(instruction, MirConst):
            values[instruction.target] = instruction.value
            return
        if isinstance(instruction, MirLoad):
            module = self.mir.module_of(module_key)
            functions = self.functions_by_module[module_key]
            if instruction.name in environment:
                values[instruction.target] = environment[instruction.name]
            elif instruction.name in functions:
                values[instruction.target] = _FunctionRef(
                    instruction.name, module_key
                )
            elif instruction.name in module.imports:
                values[instruction.target] = _ModuleRef(
                    module.imports[instruction.name]
                )
            elif instruction.name in _BUILTINS:
                values[instruction.target] = _BuiltinRef(instruction.name)
            else:
                raise MirNativeRuntimeError(f"unknown MIR load name {instruction.name!r}")
            return
        if isinstance(instruction, MirBind):
            environment[instruction.name] = self._value(values, instruction.source)
            if instruction.is_mutable:
                mutable.add(instruction.name)
            else:
                mutable.discard(instruction.name)
            return
        if isinstance(instruction, MirStore):
            if instruction.name not in environment:
                raise MirNativeRuntimeError(
                    f"store to unknown MIR binding {instruction.name!r}"
                )
            if instruction.name not in mutable:
                raise MirNativeRuntimeError(
                    f"store to immutable MIR binding {instruction.name!r}"
                )
            environment[instruction.name] = self._value(values, instruction.source)
            return
        if isinstance(instruction, MirUnary):
            operand = self._value(values, instruction.operand)
            values[instruction.target] = _unary(instruction.operator, operand)
            return
        if isinstance(instruction, MirBinary):
            left = self._value(values, instruction.left)
            right = self._value(values, instruction.right)
            values[instruction.target] = _binary(instruction.operator, left, right)
            return
        if isinstance(instruction, MirVariantIs):
            source = self._value(values, instruction.source)
            try:
                values[instruction.target] = variant_is_v1(source, instruction.variant)
            except MirVariantRuntimeError as exc:
                raise MirNativeRuntimeError(
                    f"MIR variant comparison failed closed: {exc}"
                ) from exc
            return
        if isinstance(instruction, MirVariantPayload):
            source = self._value(values, instruction.source)
            try:
                values[instruction.target] = variant_payload_v1(
                    source, instruction.variant
                )
            except MirVariantRuntimeError as exc:
                raise MirNativeRuntimeError(
                    f"MIR variant payload extraction failed closed: {exc}"
                ) from exc
            return
        if isinstance(instruction, MirStructNew):
            if len(set(instruction.required_fields)) != len(instruction.required_fields):
                raise MirNativeRuntimeError("duplicate field in sealed struct contract")
            values[instruction.target] = _StructBuilder(instruction.type_name, instruction.required_fields, {})
            return
        if isinstance(instruction, MirStructSet):
            builder = self._struct_builder(values, instruction.object)
            if builder.consumed:
                raise MirNativeRuntimeError("struct builder already consumed")
            if instruction.field not in builder.required_fields:
                raise MirNativeRuntimeError("struct field outside sealed contract")
            if instruction.field in builder.fields:
                raise MirNativeRuntimeError("duplicate struct field assignment")
            builder.fields[instruction.field] = self._value(values, instruction.source)
            return
        if isinstance(instruction, MirStructFinish):
            builder = self._struct_builder(values, instruction.source)
            if builder.consumed:
                raise MirNativeRuntimeError("struct builder already consumed")
            missing = tuple(f for f in builder.required_fields if f not in builder.fields)
            if missing:
                raise MirNativeRuntimeError("missing required struct fields: " + ", ".join(missing))
            builder.consumed = True
            values[instruction.target] = _StructValue(
                builder.type_name,
                tuple((f, builder.fields[f]) for f in builder.required_fields),
            )
            return
        if isinstance(instruction, MirList):
            values[instruction.target] = tuple(
                self._value(values, item) for item in instruction.items
            )
            return
        if isinstance(instruction, MirIterInit):
            iterable = self._value(values, instruction.iterable)
            if not isinstance(iterable, tuple):
                raise MirNativeRuntimeError("MIR iterator requires a normalized List value")
            values[instruction.target] = _ListIterator(iterable)
            return
        if isinstance(instruction, MirIterHasNext):
            iterator = self._iterator(values, instruction.iterator)
            values[instruction.target] = iterator.index < len(iterator.items)
            return
        if isinstance(instruction, MirIterNext):
            iterator = self._iterator(values, instruction.iterator)
            if iterator.index >= len(iterator.items):
                raise MirNativeRuntimeError("MIR iterator advanced past end of List")
            values[instruction.target] = iterator.items[iterator.index]
            iterator.index += 1
            return
        if isinstance(instruction, MirMember):
            receiver = self._value(values, instruction.object)
            if not isinstance(receiver, _ModuleRef):
                raise MirNativeRuntimeError(
                    "native MIR member access currently requires a module import"
                )
            functions = self.functions_by_module.get(receiver.key)
            if functions is None:
                raise MirNativeRuntimeError(
                    f"member access targets unknown MIR module {receiver.key!r}"
                )
            if instruction.member not in functions:
                raise MirNativeRuntimeError(
                    f"module has no MIR function {instruction.member!r}"
                )
            values[instruction.target] = _FunctionRef(
                instruction.member, receiver.key
            )
            return
        if isinstance(instruction, MirCall):
            callee = self._value(values, instruction.callee)
            arguments = [self._value(values, item) for item in instruction.arguments]
            values[instruction.target] = self._invoke(callee, arguments)
            return
        raise MirNativeRuntimeError(
            f"unsupported MIR instruction reached runtime: {type(instruction).__name__}"
        )

    def _invoke(self, callee: Any, arguments: list[Any]) -> Any:
        if isinstance(callee, _FunctionRef):
            module_key = callee.module_key or self.current_module_key
            functions = self.functions_by_module.get(module_key)
            if functions is None:
                raise MirNativeRuntimeError(
                    f"unknown function module {module_key!r}"
                )
            function = functions.get(callee.name)
            if function is None:
                raise MirNativeRuntimeError(f"unknown function {callee.name!r}")
            return self._call(function, arguments, module_key)
        if isinstance(callee, _BuiltinRef):
            if callee.name in {"print", "println"}:
                if len(arguments) != 1:
                    raise MirNativeRuntimeError(f"{callee.name} expects one argument")
                end = "\n" if callee.name == "println" else ""
                print(_to_string(arguments[0]), end=end)
                return _UNIT
            if callee.name == "Error":
                if len(arguments) != 1:
                    raise MirNativeRuntimeError("Error expects one argument")
                return _ErrorValue(_to_string(arguments[0]))
            if callee.name == "Some":
                if len(arguments) != 1:
                    raise MirNativeRuntimeError("Some expects one argument")
                return EnumValue("Option", "Some", arguments[0])
            if callee.name == "None":
                if arguments:
                    raise MirNativeRuntimeError("None expects zero arguments")
                return EnumValue("Option", "None")
            if callee.name == "Ok":
                if len(arguments) != 1:
                    raise MirNativeRuntimeError("Ok expects one argument")
                return EnumValue("Result", "Ok", arguments[0])
            if callee.name == "Err":
                if len(arguments) != 1:
                    raise MirNativeRuntimeError("Err expects one argument")
                return EnumValue("Result", "Err", arguments[0])
        raise MirNativeRuntimeError("MIR call target is not callable")

    @staticmethod
    def _struct_builder(values: dict[int, Any], value_id: int) -> _StructBuilder:
        value = _MirExecutor._value(values, value_id)
        if not isinstance(value, _StructBuilder):
            raise MirNativeRuntimeError("invalid MIR struct builder")
        return value

    @staticmethod
    def _value(values: dict[int, Any], value_id: int) -> Any:
        if value_id not in values:
            raise MirNativeRuntimeError(f"MIR value %{value_id} is unavailable at runtime")
        return values[value_id]

    @staticmethod
    def _iterator(values: dict[int, Any], value_id: int) -> _ListIterator:
        value = _MirExecutor._value(values, value_id)
        if not isinstance(value, _ListIterator):
            raise MirNativeRuntimeError("MIR iterator value has invalid runtime shape")
        return value


def _unary(operator: str, operand: Any) -> Any:
    if operator == "!":
        if not isinstance(operand, bool):
            raise MirNativeRuntimeError("unary ! requires Bool")
        return not operand
    if operator == "-":
        if isinstance(operand, bool) or not isinstance(operand, (int, float)):
            raise MirNativeRuntimeError("unary - requires a number")
        return -operand
    if operator == "+":
        if isinstance(operand, bool) or not isinstance(operand, (int, float)):
            raise MirNativeRuntimeError("unary + requires a number")
        return +operand
    raise MirNativeRuntimeError(f"unsupported unary operator {operator!r}")


def _binary(operator: str, left: Any, right: Any) -> Any:
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    raise MirNativeRuntimeError(f"unsupported binary operator {operator!r}")


def _to_string(value: Any) -> str:
    if value is _UNIT:
        return "unit"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = repr(value)
        if "." not in text and "e" not in text and "E" not in text:
            text += ".0"
        return text
    if isinstance(value, tuple):
        return "[" + ", ".join(_to_string(item) for item in value) + "]"
    if isinstance(value, _ErrorValue):
        return value.message
    return str(value)