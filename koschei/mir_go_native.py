"""Strict Go code generation from normalized Koschei MIR.

This backend consumes sealed MIR blocks directly and emits a program-counter
state machine for each function. Unsupported constructs are reported before
generation; this module never consults the source AST. Variant values use only
sealed ``Owner::Variant`` MIR identities and are never re-resolved by Go.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from .mir import MirFunction, MirGraph
from .mir_extension_instructions_v4 import (
    MirVariantConstruct,
    MirVariantIs,
    MirVariantPayload,
)
from .mir_ir import (
    MirAstFallback,
    MirBinary,
    MirBind,
    MirBranch,
    MirCall,
    MirConst,
    MirJump,
    MirLoad,
    MirMember,
    MirReturn,
    MirStore,
    MirUnary,
    MirUnreachable,
)
from .mir_variant_runtime_v1 import MirVariantRuntimeError, split_canonical_variant_v1
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
_ENUM_GO_TYPE = "_ksEnumValue"
_BUILTIN_VARIANTS = {
    "Option": {"Some": True, "None": False},
    "Result": {"Ok": True, "Err": True},
}


class MirGoUnsupported(ValueError):
    """Raised when a checked graph is not yet representable by MIR-Go v1."""


@dataclass(frozen=True, slots=True)
class MirGoSupport:
    supported: bool
    reasons: tuple[str, ...]


def _enum_declarations(root) -> dict[str, object]:
    return {declaration.name: declaration for declaration in root.program.enums}


def _variant_contract_reasons(mir: MirGraph) -> tuple[str, ...]:
    root = mir.root_module
    declarations = _enum_declarations(root)
    reasons: list[str] = []
    for function in root.functions:
        for block in function.blocks:
            for instruction in block.instructions:
                if not isinstance(
                    instruction,
                    (MirVariantConstruct, MirVariantIs, MirVariantPayload),
                ):
                    continue
                try:
                    owner, variant = split_canonical_variant_v1(instruction.variant)
                except MirVariantRuntimeError as exc:
                    reasons.append(
                        f"{function.name}: invalid canonical variant identity: {exc}"
                    )
                    continue

                builtin = _BUILTIN_VARIANTS.get(owner)
                if builtin is not None:
                    expects_payload = builtin.get(variant)
                    if expects_payload is None:
                        reasons.append(
                            f"{function.name}: unknown builtin variant {instruction.variant}"
                        )
                        continue
                    if isinstance(instruction, MirVariantConstruct):
                        if expects_payload != (instruction.source is not None):
                            reasons.append(
                                f"{function.name}: constructor payload shape drifted for "
                                f"{instruction.variant}"
                            )
                    if isinstance(instruction, MirVariantPayload) and not expects_payload:
                        reasons.append(
                            f"{function.name}: payload requested from payload-free "
                            f"{instruction.variant}"
                        )
                    continue

                declaration = declarations.get(owner)
                if declaration is None:
                    reasons.append(
                        f"{function.name}: canonical enum owner {owner!r} is not declared"
                    )
                    continue
                target = next(
                    (item for item in declaration.variants if item.name == variant),
                    None,
                )
                if target is None:
                    reasons.append(
                        f"{function.name}: canonical enum variant "
                        f"{instruction.variant!r} is absent"
                    )
                    continue
                expects_payload = target.payload_type is not None
                if isinstance(instruction, MirVariantConstruct):
                    if expects_payload != (instruction.source is not None):
                        reasons.append(
                            f"{function.name}: constructor payload shape drifted for "
                            f"{instruction.variant}"
                        )
                if isinstance(instruction, MirVariantPayload) and not expects_payload:
                    reasons.append(
                        f"{function.name}: payload requested from payload-free "
                        f"{instruction.variant}"
                    )
    return tuple(dict.fromkeys(reasons))


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

    enum_names = frozenset(_enum_declarations(root))
    main = next((item for item in root.functions if item.name == "main"), None)
    if main is None:
        reasons.append("MIR-Go v1 requires main")
    elif main.parameters:
        reasons.append("MIR-Go v1 requires zero-parameter main")

    function_names = {item.name for item in root.functions}
    for function in root.functions:
        if _go_type(function.return_type, allow_void=True, enum_names=enum_names) is None:
            reasons.append(
                f"{function.name}: unsupported return type {render_type(function.return_type)}"
            )
        parameter_names = {parameter.name for parameter in function.parameters}
        if len(parameter_names) != len(function.parameters):
            reasons.append(f"{function.name}: duplicate parameter")
        for parameter in function.parameters:
            if _go_type(parameter.type, allow_void=False, enum_names=enum_names) is None:
                reasons.append(
                    f"{function.name}: unsupported parameter type {render_type(parameter.type)}"
                )

        all_binding_names = {
            instruction.name
            for block in function.blocks
            for instruction in block.instructions
            if isinstance(instruction, MirBind)
        }
        known_load_names = (
            set(parameter_names)
            | all_binding_names
            | function_names
            | set(_PRINT_BUILTINS)
        )
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
                    if (
                        instruction.name in binding_names
                        or instruction.name in parameter_names
                    ) and not instruction.name.startswith("$mir_"):
                        reasons.append(
                            f"{function.name}: shadowed binding {instruction.name!r} "
                            "is not MIR-Go yet"
                        )
                    binding_names.add(instruction.name)
                    if _go_type(
                        instruction.type,
                        allow_void=False,
                        enum_names=enum_names,
                    ) is None:
                        reasons.append(
                            f"{function.name}: unsupported binding type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirStore):
                    if instruction.name not in all_binding_names:
                        reasons.append(
                            f"{function.name}: store targets unknown binding "
                            f"{instruction.name!r}"
                        )
                    if _go_type(
                        instruction.type,
                        allow_void=False,
                        enum_names=enum_names,
                    ) is None:
                        reasons.append(
                            f"{function.name}: unsupported store type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirConst):
                    if instruction.value is None:
                        reasons.append(
                            f"{function.name}: null-like MIR constant is unsupported"
                        )
                    elif _go_type(
                        instruction.type,
                        allow_void=False,
                        enum_names=enum_names,
                    ) is None:
                        reasons.append(
                            f"{function.name}: unsupported constant type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirUnary):
                    if instruction.operator not in _UNARY:
                        reasons.append(
                            f"{function.name}: unary operator "
                            f"{instruction.operator!r} unsupported"
                        )
                    if _go_type(
                        instruction.type,
                        allow_void=False,
                        enum_names=enum_names,
                    ) is None:
                        reasons.append(
                            f"{function.name}: unsupported unary result type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirBinary):
                    if instruction.operator not in _BINARY:
                        reasons.append(
                            f"{function.name}: binary operator "
                            f"{instruction.operator!r} unsupported"
                        )
                    if _go_type(
                        instruction.type,
                        allow_void=False,
                        enum_names=enum_names,
                    ) is None:
                        reasons.append(
                            f"{function.name}: unsupported binary result type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(instruction, MirLoad):
                    if instruction.name == "Error":
                        reasons.append(
                            f"{function.name}: Error values are not MIR-Go v1 yet"
                        )
                    elif instruction.name not in known_load_names:
                        reasons.append(
                            f"{function.name}: unknown static MIR load "
                            f"{instruction.name!r}"
                        )
                elif isinstance(instruction, MirCall):
                    result_type = _go_type(
                        instruction.type,
                        allow_void=True,
                        enum_names=enum_names,
                    )
                    if result_type is None:
                        reasons.append(
                            f"{function.name}: unsupported call result type "
                            f"{render_type(instruction.type)}"
                        )
                elif isinstance(
                    instruction,
                    (MirVariantConstruct, MirVariantIs, MirVariantPayload),
                ):
                    if _go_type(
                        instruction.type,
                        allow_void=False,
                        enum_names=enum_names,
                    ) is None:
                        reasons.append(
                            f"{function.name}: unsupported variant instruction type "
                            f"{render_type(instruction.type)}"
                        )
                elif not isinstance(
                    instruction,
                    (MirLoad, MirBind, MirStore, MirConst, MirUnary, MirBinary, MirCall),
                ):
                    reasons.append(
                        f"{function.name}: unsupported instruction "
                        f"{type(instruction).__name__}"
                    )

    reasons.extend(_variant_contract_reasons(mir))
    return MirGoSupport(not reasons, tuple(dict.fromkeys(reasons)))


def generate_go_mir_native(mir: MirGraph) -> str:
    support = inspect_mir_go_support(mir)
    if not support.supported:
        raise MirGoUnsupported("; ".join(support.reasons))

    root = mir.root_module
    enum_names = frozenset(_enum_declarations(root))
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
    uses_variants = any(
        isinstance(
            instruction,
            (MirVariantConstruct, MirVariantIs, MirVariantPayload),
        )
        for function in functions
        for block in function.blocks
        for instruction in block.instructions
    )

    lines = ["// Code generated from sealed Koschei MIR v4. DO NOT EDIT.", "package main", ""]
    if uses_fmt:
        lines.extend(['import "fmt"', ""])
    if uses_variants:
        lines.extend(
            [
                "type _ksEnumValue struct {",
                "\towner string",
                "\tvariant string",
                "\thasPayload bool",
                "\tpayload any",
                "}",
                "",
            ]
        )
    for function in functions:
        lines.extend(_emit_function(function, function_symbols, enum_names))
        lines.append("")
    lines.extend(["func main() {", f"\t{function_symbols['main']}()", "}", ""])
    return "\n".join(lines)


def _emit_function(
    function: MirFunction,
    function_symbols: dict[str, str],
    enum_names: frozenset[str],
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
        f"{parameter_symbols[item.name]} "
        f"{_require_go_type(item.type, enum_names=enum_names)}"
        for item in function.parameters
    )
    return_type = _require_go_type(
        function.return_type,
        allow_void=True,
        enum_names=enum_names,
    )
    signature = f"func {function_symbols[function.name]}({parameters})"
    if return_type:
        signature += f" {return_type}"
    lines = [signature + " {"]

    for name, symbol in binding_symbols.items():
        type_node = _binding_type(function, name)
        lines.append(
            f"\tvar {symbol} {_require_go_type(type_node, enum_names=enum_names)}"
        )
        lines.append(f"\t_ = {symbol}")
    for value_id, type_node in sorted(value_types.items()):
        go_type = _require_go_type(type_node, enum_names=enum_names)
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
                    enum_names=enum_names,
                )
            )
        lines.extend(_emit_terminator(block.terminator))
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


def _variant_parts(canonical: str) -> tuple[str, str]:
    try:
        return split_canonical_variant_v1(canonical)
    except MirVariantRuntimeError as exc:
        raise MirGoUnsupported(str(exc)) from exc


def _emit_instruction(
    instruction: Any,
    *,
    runtime_names: dict[str, str],
    symbolic_values: dict[int, tuple[str, str]],
    function_symbols: dict[str, str],
    enum_names: frozenset[str],
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
    if isinstance(instruction, MirVariantConstruct):
        owner, variant = _variant_parts(instruction.variant)
        owner_go = json.dumps(owner)
        variant_go = json.dumps(variant)
        if instruction.source is None:
            return [
                f"{prefix}_ks_v_{instruction.target} = _ksEnumValue{{"
                f"owner: {owner_go}, variant: {variant_go}}}"
            ]
        return [
            f"{prefix}_ks_v_{instruction.target} = _ksEnumValue{{"
            f"owner: {owner_go}, variant: {variant_go}, hasPayload: true, "
            f"payload: _ks_v_{instruction.source}}}"
        ]
    if isinstance(instruction, MirVariantIs):
        owner, variant = _variant_parts(instruction.variant)
        return [
            f"{prefix}_ks_v_{instruction.target} = "
            f"_ks_v_{instruction.source}.owner == {json.dumps(owner)} && "
            f"_ks_v_{instruction.source}.variant == {json.dumps(variant)}"
        ]
    if isinstance(instruction, MirVariantPayload):
        owner, variant = _variant_parts(instruction.variant)
        go_type = _require_go_type(instruction.type, enum_names=enum_names)
        source = f"_ks_v_{instruction.source}"
        return [
            f"{prefix}if {source}.owner != {json.dumps(owner)} || "
            f"{source}.variant != {json.dumps(variant)} || !{source}.hasPayload {{",
            f'{prefix}\tpanic("canonical variant payload proof mismatch")',
            f"{prefix}}}",
            f"{prefix}_ks_v_{instruction.target} = {source}.payload.({go_type})",
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
        if _require_go_type(
            instruction.type,
            allow_void=True,
            enum_names=enum_names,
        ):
            return [f"{prefix}_ks_v_{instruction.target} = {call}"]
        return [f"{prefix}{call}"]
    raise MirGoUnsupported(
        f"unsupported instruction reached MIR-Go emitter: {type(instruction).__name__}"
    )


def _emit_terminator(terminator: Any) -> list[str]:
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


def _binding_symbols(function: MirFunction) -> dict[str, str]:
    names: list[str] = []
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirBind) and instruction.name not in names:
                names.append(instruction.name)
    return {
        name: f"_ks_b_{index}_{_safe_identifier(name)}"
        for index, name in enumerate(names)
    }


def _binding_type(function: MirFunction, name: str) -> TypeNode:
    for block in function.blocks:
        for instruction in block.instructions:
            if isinstance(instruction, MirBind) and instruction.name == name:
                return instruction.type
    raise MirGoUnsupported(f"binding type missing for {name!r}")


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
            if (
                isinstance(instruction, MirCall)
                and isinstance(type_node, NamedType)
                and type_node.name == "Void"
            ):
                continue
            result[target] = type_node
    return result


def _go_type(
    type_node: TypeNode,
    *,
    allow_void: bool,
    enum_names: frozenset[str],
) -> str | None:
    if isinstance(type_node, UnknownType):
        return None
    if isinstance(type_node, GenericType):
        if type_node.name in _BUILTIN_VARIANTS:
            return _ENUM_GO_TYPE
        return None
    if not isinstance(type_node, NamedType):
        return None
    if type_node.name == "Void":
        return "" if allow_void else None
    scalar = _SCALAR_TYPES.get(type_node.name)
    if scalar is not None:
        return scalar
    if type_node.name in enum_names:
        return _ENUM_GO_TYPE
    return None


def _require_go_type(
    type_node: TypeNode,
    *,
    allow_void: bool = False,
    enum_names: frozenset[str],
) -> str:
    value = _go_type(
        type_node,
        allow_void=allow_void,
        enum_names=enum_names,
    )
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
