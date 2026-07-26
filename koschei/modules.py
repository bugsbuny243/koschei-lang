"""Koschei modül yükleyicisi.

`import risk` ifadesi, içe aktaran dosyanın yanındaki `risk.ks` dosyasını bağlar.
Konfigürasyon dosyası, paket bildirimi veya derleme betiği YOKTUR: dosya sistemi
tek gerçektir.

Yetki açısından kritik nokta: **import hiçbir yetki vermez.** Bir modülün
fonksiyonları, tıpkı aynı dosyadaki fonksiyonlar gibi, diske veya ağa ancak
kendilerine bir jeton parametresi verilirse dokunabilir. `main` dışında yetki
üreten hiçbir yol olmadığı için, içe aktarılan kod kendiliğinden hiçbir şey
yapamaz — bu, dilin merkezi iddiasının çok dosyalı programlardaki karşılığıdır.

Hata kodları:
    KS1601  Modül dosyası bulunamadı
    KS1602  Döngüsel import
    KS1603  Modül adı çakışması (aynı isim iki kez bağlandı)
    KS1801  Binary giriş noktası bulunamadı veya geçersiz
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .ast_nodes import Program, SourceLocation
from .integrity import check_program_integrity
from .lexer import LexerError
from .parser import ParserError, parse
from .semantic import ImportedModule, SemanticError, SemanticReport, check as semantic_check
from .typed_hir import check_typed_hir

MODULE_SUFFIX = ".ks"


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
    """Yüklenmiş tek bir modül."""

    name: str
    path: Path
    program: Program
    imports: dict[str, str] = field(default_factory=dict)
    """Yerel ad -> modül anahtarı (mutlak yol metni)."""


@dataclass(slots=True)
class ModuleGraph:
    """Kök dosyadan ulaşılabilen tüm modüller."""

    root: str
    modules: dict[str, Module]

    def module_of(self, key: str) -> Module:
        return self.modules[key]

    @property
    def root_module(self) -> Module:
        return self.modules[self.root]

    def in_dependency_order(self) -> list[Module]:
        """Bağımlılıklar kendilerini içe aktarandan ÖNCE gelir."""
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


def load_graph(root_path: str | Path) -> ModuleGraph:
    """Kök `.ks` dosyasından başlayarak tüm import grafiğini yükler."""
    root = Path(root_path).resolve()
    modules: dict[str, Module] = {}
    loading: list[str] = []

    def load(path: Path, name: str, location: SourceLocation) -> str:
        key = str(path)

        if key in loading:
            chain = " -> ".join(
                Path(item).name for item in loading[loading.index(key):]
            )
            raise ModuleError(
                "KS1602",
                f"Döngüsel import: {chain} -> {path.name}. Modüller bir halka "
                "oluşturamaz; ortak kodu üçüncü bir modüle taşıyın.",
                location,
            )

        if key in modules:
            return key

        if not path.is_file():
            raise ModuleError(
                "KS1601",
                f"Modül dosyası bulunamadı: {path.name} "
                f"(aranan yer: {path.parent})",
                location,
            )

        source = path.read_text(encoding="utf-8")
        try:
            program = parse(source)
        except (LexerError, ParserError) as error:
            error.source_path = path
            raise
        module = Module(name=name, path=path, program=program)

        loading.append(key)
        try:
            seen: set[str] = set()
            for declaration in program.imports:
                if declaration.name in seen:
                    raise ModuleError(
                        "KS1603",
                        f"'{declaration.name}' modülü birden fazla kez içe "
                        "aktarılmış.",
                        declaration.location,
                    )
                seen.add(declaration.name)

                target = path.parent / (declaration.name + MODULE_SUFFIX)
                module.imports[declaration.name] = load(
                    target, declaration.name, declaration.location
                )
        finally:
            loading.pop()

        modules[key] = module
        return key

    root_key = load(root, root.stem, SourceLocation(1, 1))
    return ModuleGraph(root=root_key, modules=modules)


def public_api(
    module: Module,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Modülün dışarıya açık fonksiyon, struct ve enum tabloları.

    v1'de bir modülün tüm üst düzey tanımları içe aktarılabilir; ayrı bir
    'pub' işareti yoktur. Bu bilinçli bir sadeleştirmedir ve ileride
    daraltılabilir — genişletmek değil daraltmak kırıcı olmadığı için.
    """
    functions = {
        declaration.name: declaration for declaration in module.program.declarations
    }
    structs = {
        declaration.name: declaration for declaration in module.program.structs
    }
    enums = {
        declaration.name: declaration for declaration in module.program.enums
    }
    return functions, structs, enums


def imported_modules(graph: ModuleGraph, module: Module) -> dict[str, ImportedModule]:
    """Bir modülün içe aktardığı modüllerin dışa açık yüzleri."""
    result: dict[str, ImportedModule] = {}
    for local_name, key in module.imports.items():
        target = graph.module_of(key)
        functions, structs, enums = public_api(target)
        result[local_name] = ImportedModule(
            local_name, functions, structs, enums
        )
    return result


def check_graph(graph: ModuleGraph) -> SemanticReport:
    """Tüm modülleri bağımlılık sırasına göre denetler; kök modülün raporunu döner.

    Her modül KENDİ ad alanında denetlenir: bir modülün fonksiyonları, onu içe
    aktaran dosyanın isimlerini göremez. Yetki kuralları modül sınırında da
    aynen geçerlidir — import hiçbir yetki taşımaz.
    """
    report: SemanticReport | None = None
    for module in graph.in_dependency_order():
        try:
            imports = imported_modules(graph, module)
            check_program_integrity(module.program)
            result = semantic_check(module.program, imports)
            check_typed_hir(module.program, imports)
        except SemanticError as error:
            error.source_path = module.path
            raise
        if module.path == graph.root_module.path:
            report = result
    assert report is not None
    return report


def require_entrypoint(graph: ModuleGraph) -> None:
    """Kök modülün çalıştırılabilir bir binary giriş noktası taşımasını zorlar.

    Normal ``check`` bir kütüphane dosyasını da doğrulayabilmelidir. Buna karşılık
    ``run``, ``build`` ve ``emit-go`` kesin olarak bir binary üretir; ``main``
    eksikliğini interpreter/Go backend aşamasına sızdırmadan burada keseriz.
    """

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
    """Modül anahtarı -> fonksiyon tablosu (yorumlayıcı için)."""
    return {
        key: {
            declaration.name: declaration
            for declaration in module.program.declarations
        }
        for key, module in graph.modules.items()
    }


def module_imports(graph: ModuleGraph) -> dict[str, dict[str, str]]:
    """Modül anahtarı -> o modülün yerel import alias tablosu."""
    return {
        key: dict(module.imports)
        for key, module in graph.modules.items()
    }


def enum_declarations(graph: ModuleGraph) -> dict[str, object]:
    """Tüm modül grafiğindeki enum tanımları (yorumlayıcı constructor tablosu)."""
    result: dict[str, object] = {}
    for module in graph.in_dependency_order():
        for declaration in module.program.enums:
            result[declaration.name] = declaration
    return result
