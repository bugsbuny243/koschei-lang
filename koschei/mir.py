"""Backend-independent MIR foundation for Koschei V5.

MIR is lowered only from compiler products that already passed Typed HIR, the
canonical effect-contract pass, and (when present) native Koschei sigil
semantics. It must not independently re-infer capability effects or sigil
meaning from AST text: doing so would create a second semantic authority after
the compiler had already decided the contracts.

Executable AST fallback instructions remain temporarily while MIR normalization
continues. Interpreter and native codegen consume this sealed graph rather than
a freshly loaded source graph.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .ast_nodes import Expression, FunctionDeclaration, Program, SourceLocation
from .capability_effect_contract_v1 import CANONICAL_CAPABILITY_EFFECTS
from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic
from .effect_contracts_v1 import EffectReport, FunctionEffects
from .mir_ir import (
    MirAstFallback,
    MirBasicBlock,
    MirBranch,
    MirJump,
    block_contract,
    validate_blocks,
)
from .mir_or_return_normalization_v1 import lower_function_blocks_v1
from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigils_v1 import NativeProgram
from .type_contracts import function_type, type_parameters_of
from .type_system import TypeNode, render_type
from .typed_hir import TypedHIRReport

MIR_VERSION = 4


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
    native_sigils: NativeSigilMir | None = None

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
            for key, module in self.modules.items():
                if module.key != key:
                    raise ValueError(
                        "MIR module identity does not match graph key: "
                        f"{module.key!r} != {key!r}"
                    )
                _assert_native_sigil_contract(module)
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
                    unknown_effects = tuple(
                        effect
                        for effect in function.effects
                        if effect not in CANONICAL_CAPABILITY_EFFECTS
                    )
                    if unknown_effects:
                        raise ValueError(
                            "MIR capability effect is outside canonical contract for "
                            f"{module.name}.{function.name}: "
                            + ", ".join(unknown_effects)
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


def _contract_import_target(target: str) -> str:
    # Authenticated object graph keys are already semantic identities and must
    # never be reinterpreted through host filesystem path rules. Legacy path
    # graphs retain their historical module-stem fingerprint contract.
    if target.startswith("koschei-object:"):
        return target
    return Path(target).stem


def _source_sigil_identities(program: Program) -> tuple[tuple[str, str], ...]:
    if not isinstance(program, NativeProgram):
        return ()
    return tuple((item.sigil, item.subject) for item in program.sigils)


def _native_sigil_identities(report: NativeSigilMir) -> tuple[tuple[str, str], ...]:
    return tuple((item.sigil, item.subject) for item in report.bindings)


def _assert_native_sigil_contract(module: MirModule) -> None:
    source_identities = _source_sigil_identities(module.program)
    report = module.native_sigils
    if source_identities and report is None:
        raise ValueError(
            f"native sigil semantics missing from canonical MIR module {module.name}"
        )
    if not source_identities and report is not None:
        raise ValueError(
            f"canonical MIR module {module.name} contains foreign native sigil semantics"
        )
    if report is None:
        return
    report.assert_sealed()
    if _native_sigil_identities(report) != source_identities:
        raise ValueError(
            f"native sigil MIR does not match source semantic roots for {module.name}"
        )


def _native_sigil_contract(report: NativeSigilMir | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "version": report.version,
        "universe_plan_digest": report.universe_plan_digest,
        "fingerprint": report.fingerprint,
        "bindings": [
            {
                "sigil": item.sigil,
                "subject": item.subject,
                "semantic_domain": item.semantic_domain,
                "may_grant_authority": item.may_grant_authority,
                "obligations": list(item.obligations),
            }
            for item in report.bindings
        ],
    }


def _native_sigil_output(report: NativeSigilMir | None) -> dict[str, Any] | None:
    contract = _native_sigil_contract(report)
    if contract is None or report is None:
        return None
    contract["bindings"] = [
        {
            "sigil": item.sigil,
            "subject": item.subject,
            "semantic_domain": item.semantic_domain,
            "may_grant_authority": item.may_grant_authority,
            "obligations": list(item.obligations),
            "source_line": item.source_line,
            "source_column": item.source_column,
        }
        for item in report.bindings
    ]
    return contract


def _program_contract(program: Program) -> dict[str, Any]:
    """Project source AST into the MIR seal without making sigil coordinates semantic.

    Existing function/control-flow source coordinates keep their historical MIR
    fingerprint behavior. Native sigil line/column is diagnostic metadata only;
    sigil semantic identity is carried by the checked NativeSigilMir contract.
    """

    payload = asdict(program)
    if isinstance(program, NativeProgram):
        payload["sigils"] = [
            {"sigil": item.sigil, "subject": item.subject} for item in program.sigils
        ]
    return payload


def _module_contract(module: MirModule) -> dict[str, Any]:
    return {
        "name": module.name,
        "program": _program_contract(module.program),
        "imports": sorted(
            (alias, _contract_import_target(target))
            for alias, target in module.imports.items()
        ),
        "native_sigils": _native_sigil_contract(module.native_sigils),
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


def _canonical_mir_effects(summary: FunctionEffects) -> tuple[str, ...]:
    """Project the checked function report onto MIR's capability-effect ABI.

    `EffectReport` also carries compiler-only facts such as authority-bearing
    signature input/output and non-capability observable effects. MIR v4's
    `effects` field represents canonical capability effects; native authority
    roots are sealed separately in the same module contract.
    """

    return tuple(
        effect for effect in summary.effects if effect in CANONICAL_CAPABILITY_EFFECTS
    )


def lower_module(
    module: Any,
    typed_report: TypedHIRReport,
    effect_report: EffectReport,
    native_sigil_mir: NativeSigilMir | None = None,
    *,
    key: str | None = None,
) -> MirModule:
    declarations = {item.name: item for item in module.program.declarations}
    if set(effect_report) != set(declarations):
        raise MirIntegrityError(
            "MIR lowering requires the exact checked effect report for every function"
        )

    source_sigil_identities = _source_sigil_identities(module.program)
    if source_sigil_identities and native_sigil_mir is None:
        raise MirIntegrityError(
            "MIR lowering refuses native sigil source without checked sigil semantics"
        )
    if not source_sigil_identities and native_sigil_mir is not None:
        raise MirIntegrityError(
            "MIR lowering refuses native sigil semantics for source without sigils"
        )
    if native_sigil_mir is not None:
        try:
            native_sigil_mir.assert_sealed()
        except ValueError as error:
            raise MirIntegrityError(f"native sigil MIR is not sealed: {error}") from error
        if _native_sigil_identities(native_sigil_mir) != source_sigil_identities:
            raise MirIntegrityError(
                "MIR lowering refuses sigil semantics that do not match source roots"
            )

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
            effect_report[declaration.name].direct_calls,
            _canonical_mir_effects(effect_report[declaration.name]),
            _resource_contract(
                declaration.name,
                effect_report[declaration.name].direct_calls,
                blocks,
            ),
            declaration,
            blocks,
        )
        for declaration in module.program.declarations
        for blocks in (lower_function_blocks_v1(declaration, typed_report),)
    )
    result = MirModule(
        str(module.path) if key is None else key,
        module.name,
        module.path,
        module.program,
        MappingProxyType(dict(module.imports)),
        functions,
        typed_report,
        native_sigil_mir,
    )
    try:
        _assert_native_sigil_contract(result)
    except ValueError as error:
        raise MirIntegrityError(str(error)) from error
    return result


def lower_graph(
    graph: Any,
    typed_reports: Mapping[str, TypedHIRReport],
    effect_reports: Mapping[str, EffectReport],
    native_sigil_reports: Mapping[str, NativeSigilMir] | None = None,
) -> MirGraph:
    if set(effect_reports) != set(graph.modules):
        raise MirIntegrityError(
            "MIR lowering requires checked effect reports for the complete module graph"
        )
    if set(typed_reports) != set(graph.modules):
        raise MirIntegrityError(
            "MIR lowering requires checked typed reports for the complete module graph"
        )

    native_reports = {} if native_sigil_reports is None else dict(native_sigil_reports)
    expected_native_keys = {
        key
        for key, module in graph.modules.items()
        if _source_sigil_identities(module.program)
    }
    if set(native_reports) != expected_native_keys:
        missing = sorted(expected_native_keys - set(native_reports))
        extra = sorted(set(native_reports) - expected_native_keys)
        raise MirIntegrityError(
            "MIR lowering requires the exact native sigil semantic report set "
            f"(missing={missing}, extra={extra})"
        )

    modules = {
        key: lower_module(
            module,
            typed_reports[key],
            effect_reports[key],
            native_reports.get(key),
            key=key,
        )
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
                "native_sigils": _native_sigil_output(module.native_sigils),
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
