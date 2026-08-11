"""Mandatory source-level effect contracts for Koschei high-assurance code.

V1 introduces `pure fn` as an enforceable promise. Effects are inferred from the
structurally typed AST and propagated through local and imported direct calls.
A pure function with any observable/authority/shared-state/unknown effect is
rejected before legacy semantic analysis or MIR lowering.

This is deliberately fail-closed. Unknown indirect calls are effects, not an
excuse to silently classify a function as pure.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from .ast_nodes import CallExpression, FunctionDeclaration, Identifier, MemberExpression, Program
from .semantic import ImportedModule, SemanticError
from .type_contracts import TypeContractValidator, function_type
from .type_system import NamedType, TypeNode, render_type
from .typed_hir import TypedHIRReport


# Effects are stable machine-readable names. A later effect-polymorphism surface
# can build on these without changing what v1 means.
_CAPABILITY_METHOD_EFFECTS: dict[str, dict[str, str]] = {
    "NetRoot": {"allow": "authority.derive"},
    "DiskRoot": {
        "allow": "authority.derive",
        "allow_read_only": "authority.derive",
    },
    "EnvRoot": {"allow": "authority.derive"},
    "ProcessRoot": {"allow": "authority.derive"},
    "NetCaps": {
        "get": "net.io",
        "post": "net.io",
        "put": "net.io",
        "delete": "net.io",
        "request": "net.io",
    },
    "DiskReadCaps": {
        "read": "disk.read",
        "read_file": "disk.read",
        "list": "disk.read",
    },
    "DiskCaps": {
        "read": "disk.read",
        "read_file": "disk.read",
        "list": "disk.read",
        "write": "disk.write",
        "write_file": "disk.write",
        "delete": "disk.write",
    },
    "EnvCaps": {"get": "env.read"},
    "ProcessCaps": {"run": "process.exec", "spawn": "process.exec"},
}

_CONSOLE_BUILTINS = {"print", "println"}
_QUEUE_BUILTINS = {
    "bounded_queue",
    "queue_try_send",
    "queue_try_recv",
    "queue_len",
    "queue_capacity",
}
_TASK_BUILTINS = {
    "task_scope",
    "task_spawn",
    "task_join_all",
    "task_pending",
    "task_capacity",
    "task_closed",
    "task_cancel",
    "task_cancel_all",
}

# These calls are deterministic/value-producing under their existing contracts.
# `parallel_map` is special-cased below so its direct worker participates in the
# transitive call graph while scheduler order remains unobservable by contract.
_PURE_BUILTINS = {
    "Error",
    "Some",
    "None",
    "Ok",
    "Err",
    "parse_json",
    "decimal",
    "decimal_add",
    "decimal_sub",
    "decimal_cmp",
    "decimal_text",
    "parallel_map",
}

_PURE_VALUE_METHODS = {
    "length",
    "to_int",
    "to_float",
    "contains",
    "trim",
    "split",
    "join",
    "get",
    "push",
    "sort",
    "keys",
    "set",
    "status",
    "text",
}


@dataclass(frozen=True, slots=True)
class FunctionEffects:
    direct_calls: tuple[str, ...]
    imported_calls: tuple[str, ...]
    direct_effects: tuple[str, ...]
    effects: tuple[str, ...]


EffectReport = dict[str, FunctionEffects]
ImportedEffectReports = dict[str, EffectReport]


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


def _base_name(type_node: TypeNode) -> str | None:
    return type_node.name if isinstance(type_node, NamedType) else getattr(type_node, "name", None)


def _signature_effects(
    function: FunctionDeclaration,
    contracts: TypeContractValidator,
) -> set[str]:
    effects: set[str] = set()
    for parameter in function.parameters:
        type_node = function_type(function, parameter.type_ref)
        if contracts.is_sensitive(type_node):
            effects.add("authority.input")
    if function.return_type is not None:
        result = function_type(function, function.return_type)
        if contracts.is_sensitive(result):
            effects.add("authority.output")
    return effects


def infer_effect_contracts(
    program: Program,
    imports: dict[str, ImportedModule],
    typed_report: TypedHIRReport,
    imported_effects: ImportedEffectReports | None = None,
) -> EffectReport:
    imported_effects = imported_effects or {}
    contracts = TypeContractValidator(program, imports)
    expression_types = {id(item.expression): item.type for item in typed_report.expressions}
    local_names = {function.name for function in program.declarations}

    direct_effects: dict[str, set[str]] = {}
    local_calls: dict[str, set[str]] = {}
    imported_calls: dict[str, set[tuple[str, str]]] = {}

    for function in program.declarations:
        effects = _signature_effects(function, contracts)
        calls: set[str] = set()
        foreign_calls: set[tuple[str, str]] = set()

        for node in _walk(function.body):
            if not isinstance(node, CallExpression):
                continue
            callee = node.callee

            if isinstance(callee, Identifier):
                name = callee.name
                if name in local_names:
                    calls.add(name)
                    continue
                if name in _CONSOLE_BUILTINS:
                    effects.add("console.write")
                    continue
                if name in _QUEUE_BUILTINS:
                    effects.add("shared-memory.queue")
                    continue
                if name in _TASK_BUILTINS:
                    effects.add("concurrency.task")
                    continue
                if name == "parallel_map":
                    if len(node.arguments) >= 2 and isinstance(node.arguments[1], Identifier):
                        worker = node.arguments[1].name
                        if worker in local_names:
                            calls.add(worker)
                        else:
                            effects.add("unknown.parallel-worker")
                    else:
                        effects.add("unknown.parallel-worker")
                    continue
                if name in _PURE_BUILTINS:
                    continue
                # Enum constructors are TYPE tokens in source but lowered into
                # identifier calls in the AST. The Typed HIR report already
                # validated those; known enum variants are pure constructors.
                if any(variant.name == name for enum in program.enums for variant in enum.variants):
                    continue
                effects.add(f"unknown.call:{name}")
                continue

            if isinstance(callee, MemberExpression):
                receiver = callee.object
                if isinstance(receiver, Identifier) and receiver.name in imports:
                    foreign_calls.add((receiver.name, callee.member))
                    continue

                receiver_type = expression_types.get(id(receiver))
                type_name = None if receiver_type is None else _base_name(receiver_type)
                effect = _CAPABILITY_METHOD_EFFECTS.get(type_name or "", {}).get(
                    callee.member
                )
                if effect is not None:
                    effects.add(effect)
                    continue

                # List.filter executes a callback. V1 refuses to guess about a
                # higher-order callback until function/effect types are explicit.
                if callee.member == "filter":
                    effects.add("unknown.higher-order")
                    continue
                if callee.member in _PURE_VALUE_METHODS:
                    continue
                effects.add(f"unknown.method:{callee.member}")
                continue

            effects.add("unknown.indirect-call")

        direct_effects[function.name] = effects
        local_calls[function.name] = calls
        imported_calls[function.name] = foreign_calls

    resolved = {name: set(items) for name, items in direct_effects.items()}

    # Imported modules are already analyzed because ModuleGraph is traversed in
    # dependency order. Bind each imported function's transitive effects now.
    for function_name, calls in imported_calls.items():
        for alias, imported_name in calls:
            report = imported_effects.get(alias)
            summary = None if report is None else report.get(imported_name)
            if summary is None:
                resolved[function_name].add(f"unknown.import:{alias}.{imported_name}")
            else:
                resolved[function_name].update(summary.effects)

    changed = True
    while changed:
        changed = False
        for function_name in sorted(local_calls):
            expanded = set(resolved[function_name])
            for callee in sorted(local_calls[function_name]):
                expanded.update(resolved[callee])
            if expanded != resolved[function_name]:
                resolved[function_name] = expanded
                changed = True

    report: EffectReport = {}
    for function in sorted(program.declarations, key=lambda item: item.name):
        foreign = tuple(
            sorted(f"{alias}.{name}" for alias, name in imported_calls[function.name])
        )
        report[function.name] = FunctionEffects(
            direct_calls=tuple(sorted(local_calls[function.name])),
            imported_calls=foreign,
            direct_effects=tuple(sorted(direct_effects[function.name])),
            effects=tuple(sorted(resolved[function.name])),
        )

    return report


def check_effect_contracts(
    program: Program,
    imports: dict[str, ImportedModule],
    typed_report: TypedHIRReport,
    imported_effects: ImportedEffectReports | None = None,
) -> EffectReport:
    report = infer_effect_contracts(program, imports, typed_report, imported_effects)
    functions = {function.name: function for function in program.declarations}

    for name in sorted(report):
        function = functions[name]
        if not function.is_pure:
            continue
        effects = report[name].effects
        if effects:
            raise SemanticError(
                "KS3940",
                f"pure fn '{name}' effect-free olmak zorundadır; bulunan effect seti: "
                + ", ".join(effects),
                function.location,
            )
    return report


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    CATALOG.setdefault(
        "KS3940",
        Diagnostic(
            "KS3940",
            "Pure effect sözleşmesi ihlal edildi",
            "pure fn gövdesi veya transitive çağrı grafiği observable/authority effect üretiyor.",
            "Pure sözleşmesi compile-time reddedildi; effect sessizce genişletilmedi.",
            "Effectful işi pure fonksiyon dışına taşıyın veya fonksiyonu pure olarak ilan etmeyin.",
            "pure fn add(a: Int, b: Int) -> Int { return a + b }",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3940",
        Diagnostic(
            "KS3940",
            "Pure effect contract violated",
            "A pure function body or its transitive call graph produces an observable/authority effect.",
            "The pure contract failed closed instead of silently widening effects.",
            "Move effectful work outside the pure function or remove the pure contract.",
            "pure fn add(a: Int, b: Int) -> Int { return a + b }",
        ),
    )


_register_diagnostics()
