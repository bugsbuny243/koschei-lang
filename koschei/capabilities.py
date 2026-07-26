"""Koschei yetki manifestosu — bir programın neye erişebildiğinin statik raporu.

Koschei'nin merkezi iddiası şudur: bir programın saldırı yüzeyi, kaynak kodunda
yazan izinlerden ibarettir. Bu modül o iddiayı **okunabilir** hale getirir:
programı çalıştırmadan, hangi kapıların açıldığını listeler.

Rapor bilinçli olarak muhafazakârdır: statik olarak çözülemeyen bir kapsam
(örneğin değişkenden gelen bir yol) 'DİNAMİK' olarak işaretlenir ve manifesto
kesin sayılmaz. Bilmediğini bildiğini iddia eden bir güvenlik raporu, rapor
olmaktan çıkar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast_nodes import (
    AssignmentExpression,
    ForStatement,
    ListLiteral,
    MapLiteral,
    StructLiteral,
    BinaryExpression,
    Block,
    CallExpression,
    Expression,
    ExpressionStatement,
    IfStatement,
    InterpolatedString,
    LetStatement,
    Literal,
    MatchExpression,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Program,
    ReturnStatement,
    SourceLocation,
    Statement,
    UnaryExpression,
    WhileStatement,
)
from .semantic import CAPABILITY_MEMBERS, NARROWED_METHODS

NARROWING_METHODS = {"allow", "allow_read_only"}

DOMAIN_TITLES = {
    "disk": "DİSK",
    "net": "AĞ",
    "env": "ORTAM DEĞİŞKENİ",
    "process": "SÜREÇ",
}

DOMAIN_ORDER = ("disk", "net", "env", "process")

DYNAMIC = "<DİNAMİK — statik olarak çözülemedi>"


@dataclass(frozen=True, slots=True)
class Grant:
    """Tek bir yetki daraltması: hangi alan, hangi kapsam, hangi erişim."""

    domain: str
    scope: str
    read_only: bool
    location: SourceLocation

    @property
    def is_dynamic(self) -> bool:
        return self.scope == DYNAMIC


@dataclass(slots=True)
class Manifest:
    grants: list[Grant] = field(default_factory=list)
    operations: dict[str, set[str]] = field(default_factory=dict)
    holder_functions: dict[str, list[str]] = field(default_factory=dict)
    required_domains: set[str] = field(default_factory=set)
    main_has_capabilities: bool = False

    @property
    def has_any(self) -> bool:
        return (
            bool(self.grants)
            or bool(self.holder_functions)
            or bool(self.required_domains)
            or self.main_has_capabilities
        )

    @property
    def is_exact(self) -> bool:
        """Dinamik veya çağırana bırakılmış kapsam yoksa manifesto kesindir."""
        granted_domains = {grant.domain for grant in self.grants}
        unresolved_requirements = self.required_domains - granted_domains
        return (
            not any(grant.is_dynamic for grant in self.grants)
            and not unresolved_requirements
        )

    def domains(self) -> list[str]:
        seen = {grant.domain for grant in self.grants} | self.required_domains
        return [domain for domain in DOMAIN_ORDER if domain in seen]

    def grants_for(self, domain: str) -> list[Grant]:
        return [grant for grant in self.grants if grant.domain == domain]


TYPE_DOMAINS = {
    "NetRoot": "net",
    "DiskRoot": "disk",
    "EnvRoot": "env",
    "ProcessRoot": "process",
    "NetCaps": "net",
    "DiskCaps": "disk",
    "DiskReadCaps": "disk",
    "EnvCaps": "env",
    "ProcessCaps": "process",
}


def _type_name_domains(
    type_name: str,
    structs: dict,
    seen: set[str] | None = None,
) -> set[str]:
    direct = TYPE_DOMAINS.get(type_name)
    if direct is not None:
        return {direct}
    declaration = structs.get(type_name)
    if declaration is None:
        return set()
    visited = set(seen or ())
    if type_name in visited:
        return set()
    visited.add(type_name)
    domains: set[str] = set()
    for field in declaration.fields:
        for field_type in field.type_ref.names:
            domains.update(_type_name_domains(field_type, structs, visited))
    return domains


def _type_ref_domains(type_ref, structs: dict) -> set[str]:
    domains: set[str] = set()
    for type_name in type_ref.names:
        domains.update(_type_name_domains(type_name, structs))
    return domains


def analyze(program: Program, imported_structs: dict | None = None) -> Manifest:
    manifest = Manifest()
    structs = {
        declaration.name: declaration for declaration in program.structs
    }
    structs.update(imported_structs or {})

    for declaration in program.declarations:
        capability_parameters = []
        parameter_domains: dict[str, set[str]] = {}
        for parameter in declaration.parameters:
            domains = _type_ref_domains(parameter.type_ref, structs)
            if (
                declaration.name == "main"
                and parameter.type_ref.names == ("SystemCaps",)
            ):
                domains = set()
            if domains:
                capability_parameters.append(parameter)
                parameter_domains[parameter.name] = domains

        if capability_parameters:
            manifest.holder_functions[declaration.name] = [
                f"{parameter.name}: {parameter.type_ref}"
                for parameter in capability_parameters
            ]
            for domains in parameter_domains.values():
                manifest.required_domains.update(domains)

        if (
            declaration.name == "main"
            and any(
                "SystemCaps" in parameter.type_ref.names
                for parameter in declaration.parameters
            )
        ):
            manifest.main_has_capabilities = True

        root_names = {
            parameter.name
            for parameter in declaration.parameters
            if "SystemCaps" in parameter.type_ref.names
        }

        # Yetki taşıyan yerel isimler -> alan eşlemesi.
        # Parametreler tipinden, 'let' ile bağlananlar daraltma çağrısından çözülür.
        bindings: dict[str, str] = {}
        for parameter in declaration.parameters:
            direct_domains = {
                TYPE_DOMAINS[type_name]
                for type_name in parameter.type_ref.names
                if type_name in TYPE_DOMAINS
            }
            if len(direct_domains) == 1:
                bindings[parameter.name] = next(iter(direct_domains))

        _collect_bindings(declaration.body, root_names, bindings)
        _scan_block(declaration.body, root_names, bindings, manifest)

    return manifest


def _collect_bindings(
    block: Block, roots: set[str], bindings: dict[str, str]
) -> None:
    """'let x = caps.disk.allow(...)' biçimindeki bağlamaları çözer."""
    for statement in block.statements:
        if isinstance(statement, LetStatement):
            value = statement.value
            if isinstance(value, CallExpression) and isinstance(
                value.callee, MemberExpression
            ):
                if value.callee.member in NARROWING_METHODS:
                    domain = _root_domain(value.callee.object, roots)
                    if domain is not None:
                        bindings[statement.name] = domain
        elif isinstance(statement, IfStatement):
            _collect_bindings(statement.then_block, roots, bindings)
            if isinstance(statement.else_branch, Block):
                _collect_bindings(statement.else_branch, roots, bindings)
            elif isinstance(statement.else_branch, IfStatement):
                _collect_bindings(
                    Block((statement.else_branch,)), roots, bindings
                )
        elif isinstance(statement, WhileStatement):
            _collect_bindings(statement.body, roots, bindings)
        elif isinstance(statement, ForStatement):
            _collect_bindings(statement.body, roots, bindings)


def _scan_block(
    block: Block, roots: set[str], bindings: dict[str, str], manifest: Manifest
) -> None:
    for statement in block.statements:
        for expression in _walk_statement(statement):
            _inspect(expression, roots, bindings, manifest)


def _inspect(
    expression: Expression,
    roots: set[str],
    bindings: dict[str, str],
    manifest: Manifest,
) -> None:
    if not isinstance(expression, CallExpression):
        return
    callee = expression.callee
    if not isinstance(callee, MemberExpression):
        return

    method = callee.member

    if method in NARROWING_METHODS:
        domain = _root_domain(callee.object, roots)
        if domain is None:
            return
        scope = _literal_text(expression.arguments[0]) if expression.arguments else DYNAMIC
        manifest.grants.append(
            Grant(
                domain=domain,
                scope=scope,
                read_only=(method == "allow_read_only"),
                location=expression.location,
            )
        )
        return

    # İşlemi, alıcının bağlı olduğu alana yazar. Metot adı tek başına yeterli
    # değildir: 'get' hem NetCaps hem EnvCaps üzerinde bulunur.
    from .ast_nodes import Identifier

    receiver = callee.object
    domain: str | None = None
    if isinstance(receiver, Identifier):
        domain = bindings.get(receiver.name)
    elif (
        isinstance(receiver, CallExpression)
        and isinstance(receiver.callee, MemberExpression)
        and receiver.callee.member in NARROWING_METHODS
    ):
        domain = _root_domain(receiver.callee.object, roots)
    if domain is not None and _is_guarded(method):
        manifest.operations.setdefault(domain, set()).add(method)


def _is_guarded(method: str) -> bool:
    return any(method in methods for methods in NARROWED_METHODS.values())


def _root_domain(expression: Expression, roots: set[str]) -> str | None:
    """'caps.disk' gibi bir kök yetki erişimini alan adına çözer."""
    if not isinstance(expression, MemberExpression):
        return None
    if expression.member not in CAPABILITY_MEMBERS:
        return None
    target = expression.object
    from .ast_nodes import Identifier  # yerel import: döngüsel bağımlılığı önler

    if isinstance(target, Identifier) and target.name in roots:
        return expression.member
    return None


def _literal_text(expression: Expression) -> str:
    if isinstance(expression, Literal) and isinstance(expression.value, str):
        return expression.value
    return DYNAMIC


def render(manifest: Manifest, source_name: str) -> str:
    lines = [f"KOSCHEI YETKİ MANİFESTOSU: {source_name}", ""]

    if not manifest.has_any:
        lines.append("Bu program hiçbir yan etki yeteneği taşımıyor.")
        lines.append(
            "Disk, ağ, ortam değişkeni ve süreç erişimi YOKTUR — saf hesaplama."
        )
        return "\n".join(lines) + "\n"

    for domain in DOMAIN_ORDER:
        grants = manifest.grants_for(domain)
        title = DOMAIN_TITLES[domain]
        if not grants:
            if domain in manifest.required_domains:
                lines.append(f"{title}:")
                lines.append(
                    f"  - {DYNAMIC}  "
                    "(capability çağıran tarafından sağlanmalıdır)"
                )
            else:
                lines.append(f"{title}: yok")
            continue

        lines.append(f"{title}:")
        for grant in grants:
            if domain == "disk":
                access = "salt-okunur" if grant.read_only else "okuma/yazma"
                label = f"  [{access}]"
            else:
                label = ""
            lines.append(
                f"  - {grant.scope}{label}  (satır {grant.location.line})"
            )
        operations = manifest.operations.get(domain)
        if operations:
            lines.append(f"  kullanılan işlemler: {', '.join(sorted(operations))}")

    if manifest.holder_functions:
        lines.append("")
        lines.append("YETKİ TAŞIYAN FONKSİYONLAR:")
        for name in sorted(manifest.holder_functions):
            parameters = ", ".join(manifest.holder_functions[name])
            lines.append(f"  - {name}({parameters})")

    lines.append("")
    if manifest.is_exact:
        lines.append(
            "Bu program yukarıda listelenen kapsamların DIŞINDA hiçbir şeye erişemez."
        )
    else:
        lines.append(
            "UYARI: en az bir kapsam statik olarak çözülemedi (dinamik değer). "
            "Manifesto KESİN DEĞİLDİR; kapsamları sabit metinlerle yazmak, "
            "programın erişim yüzeyini denetlenebilir kılar."
        )
    return "\n".join(lines) + "\n"


def to_dict(manifest: Manifest, source_name: str) -> dict:
    return {
        "source": source_name,
        "exact": manifest.is_exact,
        "has_capabilities": manifest.has_any,
        "grants": [
            {
                "domain": grant.domain,
                "scope": grant.scope,
                "read_only": grant.read_only,
                "line": grant.location.line,
                "dynamic": grant.is_dynamic,
            }
            for grant in manifest.grants
        ],
        "operations": {
            domain: sorted(names) for domain, names in sorted(manifest.operations.items())
        },
        "capability_functions": manifest.holder_functions,
        "required_domains": sorted(manifest.required_domains),
    }


# ----------------------------------------------------------------------
# AST dolaşımı
# ----------------------------------------------------------------------


def _walk_statement(statement: Statement):
    if isinstance(statement, LetStatement):
        yield from _walk_expression(statement.value)
    elif isinstance(statement, ReturnStatement):
        if statement.value is not None:
            yield from _walk_expression(statement.value)
    elif isinstance(statement, ExpressionStatement):
        yield from _walk_expression(statement.expression)
    elif isinstance(statement, IfStatement):
        yield from _walk_expression(statement.condition)
        for inner in statement.then_block.statements:
            yield from _walk_statement(inner)
        branch = statement.else_branch
        if isinstance(branch, Block):
            for inner in branch.statements:
                yield from _walk_statement(inner)
        elif isinstance(branch, IfStatement):
            yield from _walk_statement(branch)
    elif isinstance(statement, WhileStatement):
        yield from _walk_expression(statement.condition)
        for inner in statement.body.statements:
            yield from _walk_statement(inner)
    elif isinstance(statement, ForStatement):
        yield from _walk_expression(statement.iterable)
        for inner in statement.body.statements:
            yield from _walk_statement(inner)


def _walk_expression(expression: Expression):
    yield expression
    if isinstance(expression, MemberExpression):
        yield from _walk_expression(expression.object)
    elif isinstance(expression, CallExpression):
        yield from _walk_expression(expression.callee)
        for argument in expression.arguments:
            yield from _walk_expression(argument)
    elif isinstance(expression, BinaryExpression):
        yield from _walk_expression(expression.left)
        yield from _walk_expression(expression.right)
    elif isinstance(expression, UnaryExpression):
        yield from _walk_expression(expression.operand)
    elif isinstance(expression, AssignmentExpression):
        yield from _walk_expression(expression.target)
        yield from _walk_expression(expression.value)
    elif isinstance(expression, InterpolatedString):
        for part in expression.parts:
            yield from _walk_expression(part)
    elif isinstance(expression, ListLiteral):
        for item in expression.items:
            yield from _walk_expression(item)
    elif isinstance(expression, MapLiteral):
        for key, value in expression.entries:
            yield from _walk_expression(key)
            yield from _walk_expression(value)
    elif isinstance(expression, StructLiteral):
        for _, value in expression.fields:
            yield from _walk_expression(value)
    elif isinstance(expression, OrReturnExpression):
        yield from _walk_expression(expression.value)
        if expression.error is not None:
            yield from _walk_expression(expression.error)
    elif isinstance(expression, OrElseExpression):
        yield from _walk_expression(expression.value)
        yield from _walk_expression(expression.fallback)
    elif isinstance(expression, OrBlockExpression):
        yield from _walk_expression(expression.value)
        for statement in expression.handler.statements:
            yield from _walk_statement(statement)
    elif isinstance(expression, MatchExpression):
        yield from _walk_expression(expression.value)
        for arm in expression.arms:
            yield from _walk_expression(arm.body)


def analyze_graph(graph) -> Manifest:
    """Tüm modül grafiği için birleşik manifesto.

    Tek dosyaya bakmak yanıltıcı olurdu: bir programın saldırı yüzeyi, içe
    aktardığı modüllerin talep ettiği yetkileri de kapsar.
    """
    merged = Manifest()
    for module in graph.in_dependency_order():
        imported_structs = {}
        for target_key in module.imports.values():
            target = graph.module_of(target_key)
            for declaration in target.program.structs:
                imported_structs[declaration.name] = declaration
        part = analyze(module.program, imported_structs)
        merged.grants.extend(part.grants)
        for domain, operations in part.operations.items():
            merged.operations.setdefault(domain, set()).update(operations)
        for name, parameters in part.holder_functions.items():
            label = name if module.path == graph.root_module.path else f"{module.name}.{name}"
            merged.holder_functions[label] = parameters
        merged.required_domains.update(part.required_domains)
        merged.main_has_capabilities = (
            merged.main_has_capabilities or part.main_has_capabilities
        )
    return merged
