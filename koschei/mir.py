"""Backend-independent MIR foundation for Koschei V5.

This first slice deliberately keeps the executable AST nodes while sealing them
with the structural types produced by Typed HIR. Interpreter and native codegen
consume this checked graph instead of accepting a freshly loaded module graph.
Later MIR waves can replace individual AST payloads without changing the public
pipeline contract introduced here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .ast_nodes import Expression, FunctionDeclaration, Program, SourceLocation
from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic
from .effects import infer_effects
from .mir_ir import (
    MirAstFallback,
    MirBasicBlock,
    MirBranch,
    MirJump,
    block_contract,
    lower_function_blocks,
    validate_blocks,
)
from .type_contracts import function_type, type_parameters_of
from .type_system import TypeNode, render_type
from .typed_hir import TypedHIRReport

MIR_VERSION = 3


class MirIntegrityError(Exception):
    def __init__(self, message: str) -> None:
        self.code = "KS5002"
        self.message = message
        self.location = SourceLocation(1, 1)
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class MirResources:
    """Deterministic static resource summary sealed into one MIR function."""

    basic_blocks: int
    instructions: int
    ast_fallbacks: int
    backward_edges: int
    self_recursive: bool


@dataclass(frozen=True, slots=True)
class MirParameter:
    name: str
    type: TypeNode


@dataclass(frozen=True, slots=True)
class MirFunction:
    name: str
    parameters: tuple[MirParameter, ...]
    return_type: TypeNode
    calls: tuple[str, ...]
    effects: tuple[str, ...]
    resources: MirResources
    declaration: FunctionDeclaration
    blocks: tuple[MirBasicBlock, ...]


@dataclass(frozen=True, slots=True)
class MirModule:
    key: str
    name: str
    path: Path
    program: Program
    imports: Mapping[str, str]
    functions: tuple[MirFunction, ...]
    typed_report: TypedHIRReport

    def type_of(self, expression: Expression) -> TypeNode | None:
        for item in self.typed_report.expressions:
            if item.expression is expression:
                return item.type
        return None


@dataclass(frozen=True, slots=True)
class MirGraph:
    root: str
    modules: Mapping[str, MirModule]
    fingerprint: str
    version: int = MIR_VERSION

    @property
    def root_module(self) -> MirModule:
        return self.modules[self.root]

    def module_of(self, key: str) -> MirModule:
        return self.modules[key]

    def in_dependency_order(self) -> list[MirModule]:
        ordered: list[MirModule] = []
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visited:
                return
            visited.add(key)
            module = self.modules[key]
            for target in module.imports.values():
                visit(target)
            ordered.append(module)

        visit(self.root)
        return ordered

    def assert_sealed(self) -> None:
        try:
            for module in self.modules.values():
                for function in module.functions:
                    validate_blocks(function.blocks)
                    expected_resources = _resource_contract(
                        function.name,
                        function.calls,
                        function.blocks,
                    )
                    if function.resources != expected_resources:
                        raise ValueError(
                            "resource contract mismatch for "
                            f"{module.name}.{function.name}"
                        )
                expected_effects = infer_effects(module.program)
                for function in module.functions:
                    expected_calls, expected = expected_effects[function.name]
                    if function.calls != expected_calls or function.effects != expected:
                        raise ValueError(
                            f"effect contract mismatch for {module.name}.{function.name}"
                        )
            actual = _fingerprint(self.root, self.modules)
        except (KeyError, TypeError, ValueError) as error:
            raise MirIntegrityError(
                f"MIR kontrol akışı yapısal olarak geçersiz: {error}"
            ) from error
        if actual != self.fingerprint:
            raise MirIntegrityError(
                "MIR mührü kaynak ağacıyla uyuşmuyor; doğrulanmış ara temsil "
                "değiştirilmiş veya eski kalmış. Programı yeniden check edin."
            )

    def namespaces(self) -> dict[str, dict[str, FunctionDeclaration]]:
        self.assert_sealed()
        return {
            key: {item.name: item.declaration for item in module.functions}
            for key, module in self.modules.items()
        }

    def module_imports(self) -> dict[str, dict[str, str]]:
        self.assert_sealed()
        return {key: dict(module.imports) for key, module in self.modules.items()}

    def structs(self) -> dict[str, Any]:
        self.assert_sealed()
        result: dict[str, Any] = {}
        for module in self.in_dependency_order():
            for declaration in module.program.structs:
                result[declaration.name] = declaration
        return result

    def enums(self) -> dict[str, Any]:
        self.assert_sealed()
        result: dict[str, Any] = {}
        for module in self.in_dependency_order():
            for declaration in module.program.enums:
                result[declaration.name] = declaration
        return result


def _module_contract(module: MirModule) -> dict[str, Any]:
    return {
        "name": module.name,
        "program": asdict(module.program),
        "imports": sorted(
            (alias, Path(target).stem) for alias, target in module.imports.items()
        ),
        "functions": [
            {
                "name": function.name,
                "parameters": [
                    (parameter.name, render_type(parameter.type))
                    for parameter in function.parameters
                ],
                "return": render_type(function.return_type),
                "calls": list(function.calls),
                "effects": list(function.effects),
                "resources": asdict(function.resources),
                "blocks": [block_contract(block) for block in function.blocks],
            }
            for function in module.functions
        ],
        "structs": [
            {
                "name": declaration.name,
                "type_parameters": list(type_parameters_of(declaration)),
                "fields": [
                    (field.name, str(field.type_ref)) for field in declaration.fields
                ],
            }
            for declaration in module.program.structs
        ],
        "enums": [
            {
                "name": declaration.name,
                "type_parameters": list(type_parameters_of(declaration)),
                "variants": [
                    (
                        variant.name,
                        str(variant.payload_type)
                        if variant.payload_type is not None
                        else None,
                    )
                    for variant in declaration.variants
                ],
            }
            for declaration in module.program.enums
        ],
        "typed_expressions": [
            (
                type(item.expression).__name__,
                item.expression.location.line,
                item.expression.location.column,
                render_type(item.type),
            )
            for item in module.typed_report.expressions
        ],
    }


def _fingerprint(root: str, modules: Mapping[str, MirModule]) -> str:
    payload = {
        "version": MIR_VERSION,
        "root": modules[root].name,
        "modules": [
            _module_contract(module)
            for module in sorted(modules.values(), key=lambda item: item.name)
        ],
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resource_contract(
    name: str,
    calls: tuple[str, ...],
    blocks: tuple[MirBasicBlock, ...],
) -> MirResources:
    """Derive a path-independent static cost shape from sealed MIR blocks."""

    ast_fallbacks = sum(
        1
        for block in blocks
        for instruction in block.instructions
        if isinstance(instruction, MirAstFallback)
    )
    backward_edges = 0
    for block in blocks:
        terminator = block.terminator
        if isinstance(terminator, MirJump) and terminator.target <= block.id:
            backward_edges += 1
        elif isinstance(terminator, MirBranch):
            backward_edges += int(terminator.then_block <= block.id)
            backward_edges += int(terminator.else_block <= block.id)

    return MirResources(
        basic_blocks=len(blocks),
        instructions=sum(len(block.instructions) for block in blocks),
        ast_fallbacks=ast_fallbacks,
        backward_edges=backward_edges,
        self_recursive=name in calls,
    )


def lower_module(module: Any, typed_report: TypedHIRReport) -> MirModule:
    effect_contracts = infer_effects(module.program)
    functions = tuple(
        MirFunction(
            declaration.name,
            tuple(
                MirParameter(
                    parameter.name,
                    function_type(declaration, parameter.type_ref),
                )
                for parameter in declaration.parameters
            ),
            function_type(declaration, declaration.return_type),
            effect_contracts[declaration.name][0],
            effect_contracts[declaration.name][1],
            _resource_contract(
                declaration.name,
                effect_contracts[declaration.name][0],
                blocks,
            ),
            declaration,
            blocks,
        )
        for declaration in module.program.declarations
        for blocks in (lower_function_blocks(declaration, typed_report),)
    )
    return MirModule(
        str(module.path),
        module.name,
        module.path,
        module.program,
        MappingProxyType(dict(module.imports)),
        functions,
        typed_report,
    )


def lower_graph(graph: Any, typed_reports: Mapping[str, TypedHIRReport]) -> MirGraph:
    modules = {
        key: lower_module(module, typed_reports[key])
        for key, module in graph.modules.items()
    }
    result = MirGraph(graph.root, MappingProxyType(modules), "")
    object.__setattr__(result, "fingerprint", _fingerprint(result.root, result.modules))
    result.assert_sealed()
    return result


def require_mir(graph: Any) -> MirGraph:
    mir = getattr(graph, "mir", None)
    if not isinstance(mir, MirGraph):
        raise MirIntegrityError(
            "Modül grafiği MIR'a indirilmeden backend'e gönderilemez; önce "
            "check_graph çalıştırılmalıdır."
        )
    mir.assert_sealed()
    return mir


def to_dict(mir: MirGraph) -> dict[str, Any]:
    mir.assert_sealed()
    return {
        "version": mir.version,
        "fingerprint": mir.fingerprint,
        "root": mir.root_module.name,
        "modules": [
            {
                "name": module.name,
                "imports": sorted(module.imports),
                "functions": [
                    {
                        "name": function.name,
                        "parameters": [
                            {
                                "name": parameter.name,
                                "type": render_type(parameter.type),
                            }
                            for parameter in function.parameters
                        ],
                        "return": render_type(function.return_type),
                        "calls": list(function.calls),
                        "effects": list(function.effects),
                        "resources": asdict(function.resources),
                        "blocks": [
                            block_contract(block) for block in function.blocks
                        ],
                        "basic_blocks": function.resources.basic_blocks,
                        "instructions": function.resources.instructions,
                        "ast_fallbacks": function.resources.ast_fallbacks,
                    }
                    for function in module.functions
                ],
                "structs": [
                    {
                        "name": declaration.name,
                        "type_parameters": list(type_parameters_of(declaration)),
                    }
                    for declaration in module.program.structs
                ],
                "enums": [
                    {
                        "name": declaration.name,
                        "type_parameters": list(type_parameters_of(declaration)),
                    }
                    for declaration in module.program.enums
                ],
                "typed_bindings": len(module.typed_report.bindings),
                "typed_expressions": len(module.typed_report.expressions),
            }
            for module in mir.in_dependency_order()
        ],
    }


def _register_diagnostic() -> None:
    CATALOG.setdefault(
        "KS5002",
        Diagnostic(
            code="KS5002",
            title="MIR bütünlük mührü geçersiz",
            summary=(
                "Backend'e gönderilen ara temsil mühürlü değil, değiştirilmiş veya "
                "doğrulanan kaynak grafiğine göre eski kalmış."
            ),
            why=(
                "Interpreter ile native backend yalnızca aynı tip ve capability "
                "denetimlerinden geçmiş ara temsili tüketmelidir. Mühür uyuşmazlığı "
                "bu ortak güvenlik sözleşmesinin atlanmış olabileceğini gösterir."
            ),
            fix=(
                "Kaynak grafiğini yeniden `ks check` ile doğrulayın ve yalnızca "
                "üretilen mühürlü MIR'ı run/build/emit-go aşamasına geçirin."
            ),
            example="ks check .\nks mir .\nks build . -o app",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS5002",
        Diagnostic(
            code="KS5002",
            title="Invalid MIR integrity seal",
            summary=(
                "The intermediate representation passed to a backend is unsealed, "
                "modified, or stale relative to the checked source graph."
            ),
            why=(
                "The interpreter and native backend must consume the same type- and "
                "capability-checked representation. A seal mismatch means that shared "
                "security contract may have been bypassed."
            ),
            fix=(
                "Check the module graph again and pass only the resulting sealed "
                "MIR to run, build, or emit-go."
            ),
            example="ks check .\nks mir .\nks build . -o app",
        ),
    )


_register_diagnostic()
