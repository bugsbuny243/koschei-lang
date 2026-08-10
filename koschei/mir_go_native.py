"""Strict Go code generation from normalized Koschei MIR.

This backend consumes sealed MIR blocks directly and emits a program-counter
state machine for each function. Unsupported constructs are reported before
generation; this module never consults the source AST.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from .mir import MirFunction, MirGraph
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
from .type_system import GenericType, NamedType, TypeNode, UnknownType, render_type

_SCALAR_TYPES = {
    "Bool": "bool",
    "Int": "int64",
    "Float": "float64",
    "String": "string",
    "Void": "",
}
_BINARY = frozenset({"+", "-", "*", "==", "!=", "<", "<=", ">", ">="})
_UNARY = frozenset({"!", "-", "+"})
_PRINT_BUILTINS = frozenset({"print", "println"})
_GO_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]")


class MirGoUnsupported(ValueError):
    """Raised when a checked graph is not yet representable by MIR-Go v1."""


@dataclass(frozen=True, slots=True)
class MirGoSupport:
    supported: bool
    reasons: tuple[str, ...]


def inspect_mir_go_support(mir: MirGraph) -> MirGoSupport:
    mir.assert_sealed()
    reasons: list[str] = []
    if len(mir.modules) != 1:
        reasons.append("MIR-Go v1 requires a single module")
    root = mir.root_module
    if root.imports:
        reasons.append("MIR-Go v1 does not compile imports yet")
    if root.program.structs:
        reasons.append("MIR-Go v1 does not compile structs yet")
    if root.program.enums:
        reasons.append("MIR-Go v1 does not compile enums yet")

    main = next((item for item in root.functions if item.name == "main"), None)
    if main is None:
        reasons.append("MIR-Go v1 requires main")
    elif main.parameters:
        reasons.append("MIR-Go v1 requires zero-parameter main")

    function_names = {item.name for item in root.functions}
    for function in root.functions:
        if _go_type(function.return_type, allow_void=True) is None:
            reasons.append(
                f"{function.name}: unsupported return type {render_type(function.return_type)}"
            )
        parameter_names: set[str] = set()
        for parameter in function.parameters:
            if parameter.name in parameter_names:
                reasons.append(f"{function.name}: duplicate parameter {parameter.name}")
            parameter_names.add(parameter.name)
            if _go_type(parameter.type, allow_void=False) is None:
                reasons.append(
                    f"{function.name}: unsupported parameter type {render_type(parameter.type)}"
                )

        value_types = _instruction_type_map(function)
        static_loads = _static_load_names(function)
        binding_names: set[str] = set()
        for block in function.blocks:
            for instruction in block.instructions:
                if isinstance(instruction, MirAstFallback):
                    reasons.append(
                        f"{function.name}: AST fallback remains for {instruction.node_kind}"
                    )
                    continue
                if isinstance(instruction, MirMember):
                    reasons.append(f"{function.name}: member access is not MIR-Go yet")
                    continue
                if isinstance(instruction, MirBind):
                    if instruction.name in binding_names or instruction.name in parameter_names:
                        reasons.append(
                            f"{function.name}: shadowed binding {instruction.name!r} is not MIR-Go yet"
                        )
                    binding_names.add(instruction.name)
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported binding type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirStore):
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported store type {render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirConst):
                    if instruction.value is None:
                        reasons.append(f"{function.name}: null-like MIR constant is unsupported")
                    elif _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported constant type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirUnary):
                    if instruction.operator not in _UNARY:
                        reasons.append(
                            f"{function.name}: unary operator {instruction.operator!r} unsupported"
                        )
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported unary result type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirBinary):
                    if instruction.operator not in _BINARY:
                        reasons.append(
                            f"{function.name}: binary operator {instruction.operator!r} unsupported"
                        )
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported binary result type "
                            f"{render_type(instruction.type)}"
                        )
                    if instruction.operator in {"==", "!="} and (
                        _is_list_type(value_types.get(instruction.left))
                        or _is_list_type(value_types.get(instruction.right))
                    ):
                        reasons.append(
                            f"{function.name}: structural List equality is not MIR-Go v1 yet"
                        )
                elif isinstance(instruction, MirList):
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported List type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirIterInit):
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported iterator type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, (MirIterHasNext, MirIterNext)):
                    if _go_type(instruction.type, allow_void=False) is None:
                        reasons.append(
                            f"{function.name}: unsupported iterator result type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirLoad):
                    if (
                        instruction.name not in function_names
                        and instruction.name not in _PRINT_BUILTINS
                        and instruction.name == "Error"
                    ):
                        reasons.append(f"{function.name}: Error values are not MIR-Go v1 yet")
                elif isinstance(instruction, MirCall):
                    result_type = _go_type(instruction.type, allow_void=True)
                    if result_type is None:
                        reasons.append(
                            f"{function.name}: unsupported call result type "
                            f"{render_type(instruction.type)}"
                        )
                    builtin = static_loads.get(instruction.callee)
                    if builtin in _PRINT_BUILTINS and any(
                        _is_list_type(value_types.get(argument))
                        for argument in instruction.arguments
                    ):
                        reasons.append(
                            f"{function.name}: direct List printing is not MIR-Go v1 yet"
                        )
                elif not isinstance(
                    instruction,
                    (
                        MirLoad,
                        MirBind,
                        MirStore,
                        MirConst,
                        MirUnary,
                        MirBinary,
                        MirList,
                        MirIterInit,
                        MirIterHasNext,
                        MirIterNext,
                        MirCall,
                    ),
                ):
                    reasons.append(
                        f"{function.name}: unsupported instruction {type(instruction).__name__}"
                    )
    return MirGoSupport(not reasons, tuple(dict.fromkeys(reasons)))


def generate_go_mir_native(mir: MirGraph) -> str:
    support = inspect_mir_go_support(mir)
    if not support.supported:
        raise MirGoUnsupported("; ".join(support.reasons))

    root = mir.root_module
    functions = list(root.functions)
    function_symbols = {
        function.name: f"_ks_fn_{index}_{_safe_identifier(function.name)}"
        for index, function in enumerate(functions)
    }
    uses_fmt = any(
        isinstance(instruction, MirLoad) and instruction.name in _PRINT_BUILTINS
        for function in functions
        for block in function.blocks
        for instruction in block.instructions
    )
    uses_iterator = any(
        isinstance(instruction, MirIterInit)
        for function in functions
        for block in function.blocks
        for instruction in block.instructions
    )

    lines = ["// Code generated from sealed Koschei MIR v3. DO NOT EDIT.", "package main", ""]
    if uses_fmt:
        lines.extend(['import "fmt"', ""])
    if uses_iterator:
        lines.extend(
            [
                "type _ksIter[T any] struct {",
                "\titems []T",
                "\tindex int",
                "}",
                "",
            ]
        )
    for function in functions:
        lines.extend(_emit_function(function, function_symbols))
        lines.append("")
    lines.extend(["func main() {", f"\t{function_symbols['main']}()", "}", ""])
    return "\n".join(lines)


def _emit_function(
    function: MirFunction,
    function_symbols: dict[str, str],
) -> list[str]:
    binding_symbols = _binding_symbols(function)
    parameter_symbols = {
        parameter.name: f"_ks_p_{index}_{_safe_identifier(parameter.name)}"
        for index, parameter in enumerate(function.parameters)
    }
    runtime_names = {**parameter_symbols, **binding_symbols}
    symbolic_values = _symbolic_loads(function, runtime_names, function_symbols)
    value_types = _value_types(function, symbolic_values)

    parameters = ", ".join(
        f"{parameter_symbols[item.name]} {_require_go_type(item.type)}"
        for item in function.parameters
    )
    return_type = _require_go_type(function.return_type, allow_void=True)
    signature = f"func {function_symbols[function.name]}({parameters})"
    if return_type:
        signature += f" {return_type}"
    lines = [signature + " {"]

    for name, symbol in binding_symbols.items():
        type_node = _binding_type(function, name)
        lines.append(f"\tvar {symbol} {_require_go_type(type_node)}")
        lines.append(f"\t_ = {symbol}")
    for value_id, type_node in sorted(value_types.items()):
        go_type = _require_go_type(type_node)
        lines.append(f"\tvar _ks_v_{value_id} {go_type}")
        lines.append(f"\t_ = _ks_v_{value_id}")

    lines.extend(["\t_ks_pc := 0", "\tfor {", "\t\tswitch _ks_pc {"])
    for block in function.blocks:
        lines.append(f"\t\tcase {block.id}:")
        for instruction in block.instructions:
            lines.extend(
                _emit_instruction(
                    instruction,
                    runtime_names=runtime_names,
                    symbolic_values=symbolic_values,
                    function_symbols=function_symbols,
                )
            )
        lines.extend(_emit_terminator(block.terminator, function.return_type))
    lines.extend(
        [
            "\t\tdefault:",
            '\t\t\tpanic("invalid sealed Koschei MIR block")',
            "\t\t}",
            "\t}",
            "}",
        ]
    )
    return lines


def _emit_instruction(
    instruction: Any,
    *,
    runtime_names: dict[str, str],
    symbolic_values: dict[int, tuple[str, str]],
    function_symbols: dict[str, str],
) -> list[str]:
    prefix = "\t\t\t"
    if isinstance(instruction, MirConst):
        return [f"{prefix}_ks_v_{instruction.target} = {_literal(instruction.value)}"]
    if isinstance(instruction, MirLoad):
        if instruction.target in symbolic_values:
            return []
        symbol = runtime_names.get(instruction.name)
        if symbol is None:
            raise MirGoUnsupported(f"unknown MIR load {instruction.name!r}")
        return [f"{prefix}_ks_v_{instruction.target} = {symbol}"]
    if isinstance(instruction, MirBind):
        return [
            f"{prefix}{runtime_names[instruction.name]} = _ks_v_{instruction.source}"
        ]
    if isinstance(instruction, MirStore):
        return [
            f"{prefix}{runtime_names[instruction.name]} = _ks_v_{instruction.source}"
        ]
    if isinstance(instruction, MirUnary):
        return [
            f"{prefix}_ks_v_{instruction.target} = "
            f"{instruction.operator}_ks_v_{instruction.operand}"
        ]
    if isinstance(instruction, MirBinary):
        return [
            f"{prefix}_ks_v_{instruction.target} = _ks_v_{instruction.left} "
            f"{instruction.operator} _ks_v_{instruction.right}"
        ]
    if isinstance(instruction, MirList):
        go_type = _require_go_type(instruction.type)
        items = ", ".join(f"_ks_v_{item}" for item in instruction.items)
        return [f"{prefix}_ks_v_{instruction.target} = {go_type}{{{items}}}"]
    if isinstance(instruction, MirIterInit):
        go_type = _require_go_type(instruction.type)
        return [
            f"{prefix}_ks_v_{instruction.target} = "
            f"{go_type}{{items: _ks_v_{instruction.iterable}}}"
        ]
    if isinstance(instruction, MirIterHasNext):
        iterator = f"_ks_v_{instruction.iterator}"
        return [
            f"{prefix}_ks_v_{instruction.target} = "
            f"{iterator}.index < len({iterator}.items)"
        ]
    if isinstance(instruction, MirIterNext):
        iterator = f"_ks_v_{instruction.iterator}"
        return [
            f"{prefix}if {iterator}.index >= len({iterator}.items) {{",
            f'{prefix}\tpanic("sealed Koschei MIR iterator advanced past end")',
            f"{prefix}}}",
            f"{prefix}_ks_v_{instruction.target} = {iterator}.items[{iterator}.index]",
            f"{prefix}{iterator}.index++",
        ]
    if isinstance(instruction, MirCall):
        symbolic = symbolic_values.get(instruction.callee)
        if symbolic is None:
            raise MirGoUnsupported("MIR-Go v1 requires statically resolved call targets")
        kind, name = symbolic
        arguments = ", ".join(f"_ks_v_{item}" for item in instruction.arguments)
        if kind == "builtin":
            if len(instruction.arguments) != 1:
                raise MirGoUnsupported(f"{name} requires one argument")
            call = "fmt.Println" if name == "println" else "fmt.Print"
            return [f"{prefix}{call}({arguments})"]
        call = f"{function_symbols[name]}({arguments})"
        if _require_go_type(instruction.type, allow_void=True):
            return [f"{prefix}_ks_v_{instruction.target} = {call}"]
        return [f"{prefix}{call}"]
    raise MirGoUnsupported(
        f"unsupported instruction reached MIR-Go emitter: {type(instruction).__name__}"
    )


def _emit_terminator(terminator: Any, return_type: TypeNode) -> list[str]:
    prefix = "\t\t\t"
    if isinstance(terminator, MirReturn):
        if terminator.value is None:
            return [f"{prefix}return"]
        return [f"{prefix}return _ks_v_{terminator.value}"]
    if isinstance(terminator, MirJump):
        return [f"{prefix}_ks_pc = {terminator.target}", f"{prefix}continue"]
    if isinstance(terminator, MirBranch):
        return [
            f"{prefix}if _ks_v_{terminator.condition} {{",
            f"{prefix}\t_ks_pc = {terminator.then_block}",
            f"{prefix}}} else {{",
            f"{prefix}\t_ks_pc = {terminator.else_block}",
            f"{prefix}}}",
            f"{prefix}continue",
        ]
    if isinstance(terminator, MirUnreachable):
        return [f'{prefix}panic("unreachable sealed Koschei MIR block")']
    raise MirGoUnsupported(f"unsupported terminator {type(terminator).__name__}")


def _symbolic_loads(
    function: MirFunction,
    runtime_names: dict[str, str],
    function_symbols: dict[str, str],
) -> dict[int, tuple[str, str]]:
    result: dict[int, tuple[str, str]] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            if not isinstance(instruction, MirLoad):
                continue
            if instruction.name in runtime_names:
                continue
            if instruction.name in function_symbols:
                result[instruction.target] = ("function", instruction.name)
            elif instruction.name in _PRINT_BUILTINS:
                result[instruction.target] = ("builtin", instruction.name)
            else:
                raise MirGoUnsupported(f"unknown static MIR load {instruction.name!r}")
    return result


def _static_load_names(function: MirFunction) -> dict[int, str]:
    result: dict[int, str] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirLoad):
                result[instruction.target] = instruction.name
    return result


def _binding_symbols(function: MirFunction) -> dict[str, str]:
    names: list[str] = []
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirBind) and instruction.name not in names:
                names.append(instruction.name)
    return {
        name: f"_ks_b_{index}_{_safe_identifier(name)}" for index, name in enumerate(names)
    }


def _binding_type(function: MirFunction, name: str) -> TypeNode:
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirBind) and instruction.name == name:
                return instruction.type
    raise MirGoUnsupported(f"binding type missing for {name!r}")


def _instruction_type_map(function: MirFunction) -> dict[int, TypeNode]:
    result: dict[int, TypeNode] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            type_node = getattr(instruction, "type", None)
            if isinstance(target, int) and type_node is not None:
                result[target] = type_node
    return result


def _value_types(
    function: MirFunction,
    symbolic_values: dict[int, tuple[str, str]],
) -> dict[int, TypeNode]:
    result: dict[int, TypeNode] = {}
    for block in function.blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            if target is None or target in symbolic_values:
                continue
            type_node = getattr(instruction, "type", None)
            if type_node is None:
                continue
            if isinstance(instruction, MirCall) and _go_type(
                type_node, allow_void=True
            ) == "":
                continue
            result[target] = type_node
    return result


def _is_list_type(type_node: TypeNode | None) -> bool:
    return isinstance(type_node, GenericType) and type_node.name == "List"


def _go_type(type_node: TypeNode, *, allow_void: bool) -> str | None:
    if isinstance(type_node, UnknownType):
        return None
    if isinstance(type_node, NamedType):
        if type_node.name == "Void":
            return "" if allow_void else None
        return _SCALAR_TYPES.get(type_node.name)
    if isinstance(type_node, GenericType) and len(type_node.arguments) == 1:
        argument = _go_type(type_node.arguments[0], allow_void=False)
        if argument is None:
            return None
        if type_node.name == "List":
            return f"[]{argument}"
        if type_node.name == "Iterator":
            return f"_ksIter[{argument}]"
    return None


def _require_go_type(type_node: TypeNode, *, allow_void: bool = False) -> str:
    value = _go_type(type_node, allow_void=allow_void)
    if value is None:
        raise MirGoUnsupported(f"unsupported MIR-Go type {render_type(type_node)}")
    return value


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    raise MirGoUnsupported(f"unsupported MIR literal {value!r}")


def _safe_identifier(value: str) -> str:
    cleaned = _GO_IDENTIFIER.sub("_", value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned
