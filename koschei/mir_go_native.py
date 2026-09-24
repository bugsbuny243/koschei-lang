"""NON-AUTHORITATIVE host conformance adapter for sealed Koschei MIR.

ARCHITECTURAL STATUS
====================
This module is bootstrap/conformance machinery only. It is NOT the Koschei
native runtime, does not define Koschei language semantics, and must never be
used to repair, infer, reinterpret, or extend compiler-owned facts.

Canonical execution meaning is owned by the sealed Koschei MIR/state-transition
contract described by ``KOSCHEI_NATIVE_EXECUTION_BOUNDARY_V1.md``. This adapter
may only project already-sealed facts into a Go program and must fail closed
when that projection is incomplete.

The historical module name is retained temporarily to avoid a broad import/API
migration inside the same production branch. New architecture and production
claims must classify it as a host conformance adapter, not as Koschei-native.

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
    """Raised when sealed Koschei MIR cannot be projected by this host adapter."""


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
                label = f"{root.name}.{function.name}"
                try:
                    owner, variant = split_canonical_variant_v1(instruction.variant)
                except MirVariantRuntimeError as exc:
                    reasons.append(f"{label}: invalid canonical variant identity: {exc}")
                    continue
                builtin = _BUILTIN_VARIANTS.get(owner)
                if builtin is not None:
                    expects_payload = builtin.get(variant)
                    if expects_payload is None:
                        reasons.append(f"{label}: unknown builtin canonical variant {instruction.variant}")
                        continue
                    if isinstance(instruction, MirVariantConstruct):
                        if expects_payload != (instruction.source is not None):
                            reasons.append(f"{label}: constructor payload shape drifted for {instruction.variant}")
                    if isinstance(instruction, MirVariantPayload) and not expects_payload:
                        reasons.append(f"{label}: payload requested from payload-free {instruction.variant}")
                    continue
                declaration = declarations.get(owner)
                if declaration is None:
                    reasons.append(f"{label}: unknown canonical enum owner {owner!r}")
                    continue
                target = next((item for item in declaration.variants if item.name == variant), None)
                if target is None:
                    reasons.append(f"{label}: unknown canonical enum variant {instruction.variant!r}")
                    continue
                expects_payload = target.payload_type is not None
                if isinstance(instruction, MirVariantConstruct):
                    if expects_payload != (instruction.source is not None):
                        reasons.append(f"{label}: constructor payload shape drifted for {instruction.variant}")
                if isinstance(instruction, MirVariantPayload) and not expects_payload:
                    reasons.append(f"{label}: payload requested from payload-free {instruction.variant}")
    return tuple(dict.fromkeys(reasons))


def _type_to_go(type_node: TypeNode) -> str | None:
    if isinstance(type_node, NamedType):
        if type_node.name in _SCALAR_TYPES:
            return _SCALAR_TYPES[type_node.name]
        return _ENUM_GO_TYPE
    if isinstance(type_node, GenericType):
        if type_node.name in {"Option", "Result"}:
            return _ENUM_GO_TYPE
    if isinstance(type_node, UnknownType):
        return None
    return None


def _go_ident(name: str) -> str:
    value = _GO_IDENTIFIER.sub("_", name)
    if not value or value[0].isdigit():
        value = "_" + value
    return value


def _value_name(value_id: int) -> str:
    return f"v{value_id}"


def _literal(value: Any) -> str:
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return repr(value)
    raise MirGoUnsupported(f"unsupported constant for host projection: {value!r}")


def inspect_mir_go_support(mir: MirGraph) -> MirGoSupport:
    """Report whether this non-authoritative host adapter can project the graph."""
    reasons: list[str] = []
    if len(mir.modules) != 1:
        reasons.append("host adapter v1 supports one module only")
    root = mir.root_module
    if root.program.imports:
        reasons.append("host adapter v1 does not project imports")
    if root.program.structs:
        reasons.append("host adapter v1 does not project structs")
    reasons.extend(_variant_contract_reasons(mir))
    for function in root.functions:
        if _type_to_go(function.return_type) is None:
            reasons.append(f"{function.name}: unsupported return type {render_type(function.return_type)}")
        for parameter in function.parameters:
            if _type_to_go(parameter.type_node) is None:
                reasons.append(f"{function.name}: unsupported parameter type {render_type(parameter.type_node)}")
        for block in function.blocks:
            for instruction in block.instructions:
                if isinstance(instruction, MirAstFallback):
                    reasons.append(f"{function.name}: AST fallback is forbidden at sealed host boundary")
                elif not isinstance(
                    instruction,
                    (
                        MirConst, MirBind, MirLoad, MirStore, MirBinary, MirUnary,
                        MirMember, MirCall, MirJump, MirBranch, MirReturn,
                        MirUnreachable, MirVariantConstruct, MirVariantIs,
                        MirVariantPayload,
                    ),
                ):
                    reasons.append(f"{function.name}: unsupported sealed MIR instruction {type(instruction).__name__}")
    return MirGoSupport(not reasons, tuple(dict.fromkeys(reasons)))


def _function_signature(function: MirFunction) -> str:
    params = []
    for parameter in function.parameters:
        go_type = _type_to_go(parameter.type_node)
        if go_type is None:
            raise MirGoUnsupported(f"unsupported parameter type {render_type(parameter.type_node)}")
        params.append(f"{_go_ident(parameter.name)} {go_type}")
    result = _type_to_go(function.return_type)
    if result is None:
        raise MirGoUnsupported(f"unsupported return type {render_type(function.return_type)}")
    suffix = f" {result}" if result else ""
    return f"func {_go_ident(function.name)}({', '.join(params)}){suffix}"


def _zero_value(go_type: str) -> str:
    if go_type == "bool": return "false"
    if go_type in {"int64", "float64"}: return "0"
    if go_type == "string": return '""'
    if go_type == _ENUM_GO_TYPE: return f"{_ENUM_GO_TYPE}{{}}"
    return "nil"


def _emit_function(function: MirFunction) -> list[str]:
    lines = [_function_signature(function) + " {"]
    values: set[int] = set()
    variables: dict[str, str] = {}
    mutable: set[str] = set()
    for parameter in function.parameters:
        variables[parameter.name] = _go_ident(parameter.name)
    for block in function.blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            if isinstance(target, int): values.add(target)
    for value_id in sorted(values):
        lines.append(f"    var {_value_name(value_id)} any")
    lines.append(f"    pc := {function.entry_block}")
    lines.append("    for {")
    lines.append("        switch pc {")
    for block in function.blocks:
        lines.append(f"        case {block.id}:")
        for instruction in block.instructions:
            if isinstance(instruction, MirConst):
                lines.append(f"            {_value_name(instruction.target)} = {_literal(instruction.value)}")
            elif isinstance(instruction, MirBind):
                name = _go_ident(instruction.name)
                if instruction.name not in variables:
                    variables[instruction.name] = name
                    lines.append(f"            var {name} any")
                lines.append(f"            {name} = {_value_name(instruction.source)}")
                if instruction.mutable: mutable.add(instruction.name)
            elif isinstance(instruction, MirLoad):
                name = variables.get(instruction.name)
                if name is None: raise MirGoUnsupported(f"unknown sealed load {instruction.name!r}")
                lines.append(f"            {_value_name(instruction.target)} = {name}")
            elif isinstance(instruction, MirStore):
                name = variables.get(instruction.name)
                if name is None or instruction.name not in mutable:
                    raise MirGoUnsupported(f"invalid sealed store {instruction.name!r}")
                lines.append(f"            {name} = {_value_name(instruction.source)}")
            elif isinstance(instruction, MirBinary):
                if instruction.operator in {"+", "-", "*"}:
                    lines.append(
                        f"            {_value_name(instruction.target)} = "
                        f"{_value_name(instruction.left)}.(int64) "
                        f"{instruction.operator} "
                        f"{_value_name(instruction.right)}.(int64)"
                    )
                else:
                    lines.append(
                        f"            {_value_name(instruction.target)} = "
                        f"fmt.Sprint({_value_name(instruction.left)}) "
                        f"{instruction.operator} "
                        f"fmt.Sprint({_value_name(instruction.right)})"
                    )
            elif isinstance(instruction, MirUnary):
                if instruction.operator == "!": lines.append(f"            {_value_name(instruction.target)} = !{_value_name(instruction.operand)}.(bool)")
                else: lines.append(f"            {_value_name(instruction.target)} = {instruction.operator}{_value_name(instruction.operand)}.(int64)")
            elif isinstance(instruction, MirMember):
                raise MirGoUnsupported("member projection is not yet supported by host adapter")
            elif isinstance(instruction, MirCall):
                args = ", ".join(_value_name(arg) for arg in instruction.arguments)
                if instruction.callee in _PRINT_BUILTINS:
                    call = "fmt.Println" if instruction.callee == "println" else "fmt.Print"
                    lines.append(f"            {call}({args})")
                    if instruction.target is not None: lines.append(f"            {_value_name(instruction.target)} = nil")
                else:
                    target = _go_ident(instruction.callee)
                    if instruction.target is None: lines.append(f"            {target}({args})")
                    else: lines.append(f"            {_value_name(instruction.target)} = {target}({args})")
            elif isinstance(instruction, MirVariantConstruct):
                owner, variant = split_canonical_variant_v1(instruction.variant)
                payload = "nil" if instruction.source is None else _value_name(instruction.source)
                has_payload = "false" if instruction.source is None else "true"
                lines.append(f"            {_value_name(instruction.target)} = {_ENUM_GO_TYPE}{{owner: {json.dumps(owner)}, variant: {json.dumps(variant)}, hasPayload: {has_payload}, payload: {payload}}}")
            elif isinstance(instruction, MirVariantIs):
                owner, variant = split_canonical_variant_v1(instruction.variant)
                source = _value_name(instruction.source)
                lines.append(f"            _e, _ok := {source}.({_ENUM_GO_TYPE})")
                lines.append(f"            {_value_name(instruction.target)} = _ok && _e.owner == {json.dumps(owner)} && _e.variant == {json.dumps(variant)}")
            elif isinstance(instruction, MirVariantPayload):
                owner, variant = split_canonical_variant_v1(instruction.variant)
                source = _value_name(instruction.source)
                lines.append(f"            _e, _ok := {source}.({_ENUM_GO_TYPE})")
                lines.append(f"            if !_ok || _e.owner != {json.dumps(owner)} || _e.variant != {json.dumps(variant)} || !_e.hasPayload {{ panic(\"sealed Koschei variant proof violated\") }}")
                lines.append(f"            {_value_name(instruction.target)} = _e.payload")
        terminator = block.terminator
        if isinstance(terminator, MirJump):
            lines.append(f"            pc = {terminator.target}")
            lines.append("            continue")
        elif isinstance(terminator, MirBranch):
            lines.append(f"            if {_value_name(terminator.condition)}.(bool) {{ pc = {terminator.if_true} }} else {{ pc = {terminator.if_false} }}")
            lines.append("            continue")
        elif isinstance(terminator, MirReturn):
            if terminator.value is None: lines.append("            return")
            else: lines.append(f"            return {_value_name(terminator.value)}.({_type_to_go(function.return_type)})")
        elif isinstance(terminator, MirUnreachable):
            lines.append('            panic("sealed Koschei unreachable state reached")')
        else:
            raise MirGoUnsupported(f"unsupported terminator {type(terminator).__name__}")
    lines.append("        default:")
    lines.append('            panic("invalid sealed Koschei program counter")')
    lines.append("        }")
    lines.append("    }")
    lines.append("}")
    return lines


def emit_go_from_mir(mir: MirGraph) -> str:
    """Project sealed Koschei MIR into Go without acquiring semantic authority."""
    mir.assert_sealed()
    support = inspect_mir_go_support(mir)
    if not support.supported:
        raise MirGoUnsupported("; ".join(support.reasons))
    root = mir.root_module
    lines = [
        "// Generated host conformance projection from sealed Koschei MIR.",
        "// NON-AUTHORITATIVE: Koschei semantics are owned by the sealed MIR contract.",
        "package main",
        "",
        'import "fmt"',
        "",
        f"type {_ENUM_GO_TYPE} struct {{",
        "    owner string",
        "    variant string",
        "    hasPayload bool",
        "    payload any",
        "}",
        "",
    ]
    for function in root.functions:
        lines.extend(_emit_function(function))
        lines.append("")
    if not any(function.name == "main" for function in root.functions):
        raise MirGoUnsupported("sealed graph has no main function")
    return "\n".join(lines)


__all__ = ["MirGoSupport", "MirGoUnsupported", "emit_go_from_mir", "inspect_mir_go_support"]
