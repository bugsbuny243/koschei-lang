"""Koschei module loader.

By default, `import risk` binds `risk.ks` beside the importing file. Callers that
need a stronger project system may supply an explicit resolver, but import never
grants authority: imported code can use disk/network/env/process effects only
through capability values that are actually passed to it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .affine_resources_v1 import check_affine_resources
from .ast_nodes import Program, SourceLocation
from .effect_contracts_v1 import EffectReport, check_effect_contracts
from .integrity import check_program_integrity
from .legacy_generics import prepare_legacy_analysis
from .lexer import LexerError
from .mir import lower_graph as lower_mir_graph
from .parser import ParserError, parse
from .semantic import ImportedModule, SemanticError, SemanticReport, check as semantic_check
from .typed_hir import check_typed_hir
from .typestate_resources_v1 import check_typestate_resources

MODULE_SUFFIX = ".ks"
ImportResolver = Callable[[Path, str, SourceLocation], Path]


class ModuleError(Exception):
    def __init__(self, code: str, message: str, location: SourceLocation) -> None:
        self.code = code
        self.message = message
        self.location = location
        super().__init__(
            f"{code} [satır {location.line}, sütun {location.column}]: {message}"
        )


@dataclass(slots=True)
class Module:
    name: str
    path: Path
    program: Program
    imports: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ModuleGraph:
    root: str
    modules: dict[str, Module]
    mir: object | None = None

    def module_of(self, key: str) -> Module:
        return self.modules[key]

    @property
    def root_module(self) -> Module:
        return self.modules[self.root]

    def in_dependency_order(self) -> list[Module]:
        ordered: list[Module] = []
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


def load_graph(
    root_path: str | Path,
    *,
    import_resolver: ImportResolver | None = None,
) -> ModuleGraph:
    root = Path(root_path).resolve()
    resolver = import_resolver or _resolve_sibling_import
    modules: dict[str, Module] = {}
    loading: list[str] = []

    def load(path: Path, name: str, location: SourceLocation) -> str:
        resolved_path = path.resolve(strict=False)
        key = str(resolved_path)
        if key in loading:
            chain = " -> ".join(
                Path(item).name for item in loading[loading.index(key) :]
            )
            raise ModuleError(
                "KS1602",
                f"Döngüsel import: {chain} -> {resolved_path.name}. Modüller bir halka "
                "oluşturamaz; ortak kodu üçüncü bir modüle taşıyın.",
                location,
            )
        if key in modules:
            return key
        if not resolved_path.is_file():
            raise ModuleError(
                "KS1601",
                f"Modül dosyası bulunamadı: {resolved_path.name} "
                f"(aranan yer: {resolved_path.parent})",
                location,
            )

        source = resolved_path.read_text(encoding="utf-8")
        try:
            program = parse(source)
        except (LexerError, ParserError) as error:
            error.source_path = resolved_path
            raise
        module = Module(name=name, path=resolved_path, program=program)

        loading.append(key)
        try:
            seen: set[str] = set()
            for declaration in program.imports:
                if declaration.name in seen:
                    raise ModuleError(
                        "KS1603",
                        f"'{declaration.name}' modülü birden fazla kez içe aktarılmış.",
                        declaration.location,
                    )
                seen.add(declaration.name)
                target = resolver(
                    resolved_path,
                    declaration.name,
                    declaration.location,
                )
                module.imports[declaration.name] = load(
                    target,
                    declaration.name,
                    declaration.location,
                )
        finally:
            loading.pop()

        modules[key] = module
        return key

    root_key = load(root, root.stem, SourceLocation(1, 1))
    return ModuleGraph(root=root_key, modules=modules)


def _resolve_sibling_import(
    importer: Path,
    name: str,
    _location: SourceLocation,
) -> Path:
    return importer.parent / (name + MODULE_SUFFIX)


def public_api(
    module: Module,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    functions = {
        declaration.name: declaration for declaration in module.program.declarations
    }
    structs = {declaration.name: declaration for declaration in module.program.structs}
    enums = {declaration.name: declaration for declaration in module.program.enums}
    return functions, structs, enums


def imported_modules(graph: ModuleGraph, module: Module) -> dict[str, ImportedModule]:
    result: dict[str, ImportedModule] = {}
    for local_name, key in module.imports.items():
        target = graph.module_of(key)
        functions, structs, enums = public_api(target)
        result[local_name] = ImportedModule(local_name, functions, structs, enums)
    return result


def check_graph(graph: ModuleGraph) -> SemanticReport:
    # Fail closed: a new check invalidates any previously attached MIR before
    # analysis starts, so a failed re-check can never leave a stale backend input.
    graph.mir = None
    report: SemanticReport | None = None
    typed_reports = {}
    effect_reports: dict[str, EffectReport] = {}

    # Module.path is a diagnostic/source locator, not semantic identity. Ordinary
    # path-based projects currently use path strings as graph keys, but stronger
    # project systems may use authenticated object identities. Never reconstruct
    # analysis identity from the locator or imported effect propagation can be
    # silently skipped when a non-path graph key is used.
    key_by_module_identity = {
        id(module): key for key, module in graph.modules.items()
    }

    for module in graph.in_dependency_order():
        module_key = key_by_module_identity[id(module)]
        try:
            imports = imported_modules(graph, module)
            check_program_integrity(module.program)
            typed_report = check_typed_hir(module.program, imports)
            check_typestate_resources(module.program, imports, typed_report)
            check_affine_resources(module.program, imports, typed_report)

            imported_effects = {
                alias: effect_reports[target]
                for alias, target in module.imports.items()
                if target in effect_reports
            }
            effect_report = check_effect_contracts(
                module.program,
                imports,
                typed_report,
                imported_effects,
            )
            effect_reports[module_key] = effect_report
            typed_reports[module_key] = typed_report

            legacy_program, legacy_imports = prepare_legacy_analysis(
                module.program,
                imports,
                typed_report,
            )
            result = semantic_check(legacy_program, legacy_imports)
        except SemanticError as error:
            error.source_path = module.path
            raise
        if module_key == graph.root:
            report = result
    assert report is not None
    graph.mir = lower_mir_graph(graph, typed_reports)
    return report


def require_entrypoint(graph: ModuleGraph) -> None:
    main = next(
        (
            declaration
            for declaration in graph.root_module.program.declarations
            if declaration.name == "main"
        ),
        None,
    )
    if main is None:
        raise ModuleError(
            "KS1801",
            "Binary hedefi için kök modülde 'fn main()' giriş noktası bulunmalıdır.",
            SourceLocation(1, 1),
        )
    if main.return_type is not None:
        raise ModuleError(
            "KS1801",
            "Bu sürümde 'main' dönüş tipi bildiremez; başarı/hata akışı "
            "Result ve 'or return' ile yönetilmelidir.",
            main.return_type.location,
        )


def namespaces(graph: ModuleGraph) -> dict[str, dict]:
    return {
        key: {
            declaration.name: declaration
            for declaration in module.program.declarations
        }
        for key, module in graph.modules.items()
    }


def module_imports(graph: ModuleGraph) -> dict[str, dict[str, str]]:
    return {key: dict(module.imports) for key, module in graph.modules.items()}


def struct_declarations(graph: ModuleGraph) -> dict[str, object]:
    result: dict[str, object] = {}
    for module in graph.in_dependency_order():
        for declaration in module.program.structs:
            result[declaration.name] = declaration
    return result


def enum_declarations(graph: ModuleGraph) -> dict[str, object]:
    result: dict[str, object] = {}
    for module in graph.in_dependency_order():
        for declaration in module.program.enums:
            result[declaration.name] = declaration
    return result
