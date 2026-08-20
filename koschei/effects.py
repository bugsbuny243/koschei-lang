"""Fail-closed capability/effect inference for sealed MIR."""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from .ast_nodes import CallExpression, FunctionDeclaration, Identifier, MemberExpression, Program
from .capability_effect_contract_v1 import effect_for


def _walk(value: Any):
    if is_dataclass(value):
        yield value
        for field in fields(value):
            yield from _walk(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)


def _direct(function: FunctionDeclaration, local_names: set[str]) -> tuple[set[str], set[str]]:
    parameter_types = {parameter.name: str(parameter.type_ref) for parameter in function.parameters}
    effects: set[str] = set()
    calls: set[str] = set()
    for node in _walk(function.body):
        if not isinstance(node, CallExpression):
            continue
        if isinstance(node.callee, Identifier) and node.callee.name in local_names:
            calls.add(node.callee.name)
        if not isinstance(node.callee, MemberExpression):
            continue
        receiver = node.callee.object
        if not isinstance(receiver, Identifier):
            continue
        effect = effect_for(parameter_types.get(receiver.name, ""), node.callee.member)
        if effect is not None:
            effects.add(effect)
    return effects, calls


def infer_effects(program: Program) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    names = {function.name for function in program.declarations}
    direct: dict[str, set[str]] = {}
    calls: dict[str, set[str]] = {}
    for function in program.declarations:
        direct[function.name], calls[function.name] = _direct(function, names)
    resolved = {name: set(items) for name, items in direct.items()}
    changed = True
    while changed:
        changed = False
        for name, callees in calls.items():
            expanded = (
                resolved[name] | set().union(*(resolved[callee] for callee in callees))
                if callees
                else resolved[name]
            )
            if expanded != resolved[name]:
                resolved[name] = expanded
                changed = True
    return {
        name: (tuple(sorted(calls[name])), tuple(sorted(resolved[name])))
        for name in sorted(names)
    }
