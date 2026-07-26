"""Koschei AST için semantic ve capability güvenlik denetleyicisi.

Hata kodları:
    KS1101  Tanımsız isim
    KS1102  Aynı scope içinde tekrar tanım
    KS1201  Immutable değere atama
    KS1301  Tip uyuşmazlığı
    KS1302  Int literal işaretli 64-bit aralığın dışında
    KS1401  Ele alınmayan hata değeri
    KS1501  Struct literalinde alan hatası (eksik, bilinmeyen veya yinelenen)
    KS1502  Struct'ta böyle bir alan yok
    KS1604  İki modül aynı struct adını tanımlıyor
    KS1605  Modülde böyle bir fonksiyon veya struct yok
    KS1701  Enum veya varyant sözleşmesi hatası
    KS1702  match exhaustive değil veya kol sözleşmesi hatalı
    KS2401  Gerekli yetki bu scope içinde mevcut değil
    KS2402  Kök yetki doğrudan kullanılamaz (önce allow ile daraltılmalı)
    KS2403  Daraltılmış yetki yeniden genişletilemez
    KS2404  Bu yetki türü ilgili işleme izin vermez
    KS2405  Ağ origin şeması HTTP/HTTPS değil

Yetki modeli:
    caps.disk           -> DiskRoot   (yalnızca allow / allow_read_only)
    DiskRoot.allow(...) -> DiskCaps   (read/write/list/delete; allow YOK)
    DiskRoot.allow_read_only(...) -> DiskReadCaps (yalnızca read/list)
Kök tipler G/Ç yapamaz; daraltılmış tipler yeniden allow çağıramaz.
Böylece daraltma tek yönlüdür ve derleme zamanında zorlanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .ast_nodes import (
    AssignmentExpression,
    EnumDeclaration,
    EnumVariant,
    ForStatement,
    ListLiteral,
    MapLiteral,
    StructLiteral,
    BinaryExpression,
    Block,
    CallExpression,
    Expression,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
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


CAPABILITY_MEMBERS = {
    "net": "NetRoot",
    "disk": "DiskRoot",
    "env": "EnvRoot",
    "process": "ProcessRoot",
}

ROOT_METHODS: dict[str, dict[str, str]] = {
    "NetRoot": {"allow": "NetCaps"},
    "DiskRoot": {"allow": "DiskCaps", "allow_read_only": "DiskReadCaps"},
    "EnvRoot": {"allow": "EnvCaps"},
    "ProcessRoot": {"allow": "ProcessCaps"},
}

NARROWED_METHODS: dict[str, set[str]] = {
    "NetCaps": {"get", "post", "put", "delete", "request"},
    "DiskCaps": {"read", "write", "delete", "list", "read_file", "write_file"},
    "DiskReadCaps": {"read", "list", "read_file"},
    "EnvCaps": {"get"},
    "ProcessCaps": {"run", "spawn"},
}

NARROWING_METHODS = {"allow", "allow_read_only"}

GUARDED_METHODS: set[str] = set()
for _methods in NARROWED_METHODS.values():
    GUARDED_METHODS.update(_methods)

CAPABILITY_TYPES = set(ROOT_METHODS) | set(NARROWED_METHODS) | {"SystemCaps"}
ROOT_CAPABILITY_TYPES = set(ROOT_METHODS) | {"SystemCaps"}
NET_ORIGIN_SCHEMES = frozenset({"http", "https"})

BUILTIN_CALLS = {
    "print",
    "println",
    "Error",
    "Some",
    "None",
    "Ok",
    "Err",
    "parse_json",
}

# List üzerinde çağrılabilen metotlar. 'get' aynı zamanda bir yetki metodu
# adı olduğu için alıcının tipi ÖNCE denetlenir; aksi hâlde liste erişimi
# yanlışlıkla yetki ihlali sayılırdı.
STRING_METHODS = {
    "length",
    "to_int",
    "to_float",
    "contains",
    "trim",
    "split",
    "join",
}
LIST_METHODS = {"length", "get", "push", "contains", "sort", "filter"}
MAP_METHODS = {"get", "set", "keys", "contains"}

COMPARISON_OPERATORS = {"==", "!=", "<", "<=", ">", ">="}
LOGICAL_OPERATORS = {"&&", "||"}
ARITHMETIC_OPERATORS = {"+", "-", "*", "/"}
NUMERIC_TYPES = {"Int", "Float"}
INT_MIN = -(1 << 63)
INT_MAX = (1 << 63) - 1
INT_MIN_MAGNITUDE = 1 << 63


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    type_name: str | None
    is_mutable: bool
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class SemanticReport:
    functions: int
    variables: int
    capability_values: int


class SemanticError(Exception):
    def __init__(self, code: str, message: str, location: SourceLocation) -> None:
        self.code = code
        self.message = message
        self.location = location
        super().__init__(
            f"{code} [satır {location.line}, sütun {location.column}]: {message}"
        )


MODULE_TYPE_PREFIX = "Module:"


class ImportedModule:
    """İçe aktarılmış bir modülün dışarıya açık yüzü."""

    __slots__ = ("name", "functions", "structs", "enums")

    def __init__(
        self,
        name: str,
        functions: dict,
        structs: dict,
        enums: dict | None = None,
    ) -> None:
        self.name = name
        self.functions = functions
        self.structs = structs
        self.enums = enums or {}


class SemanticChecker:
    def __init__(
        self, program: Program, imports: dict[str, ImportedModule] | None = None
    ) -> None:
        self.program = program
        self.imports = imports or {}
        self.functions = {declaration.name: declaration for declaration in program.declarations}
        self.structs = {
            declaration.name: declaration for declaration in program.structs
        }
        self.enums = {
            declaration.name: declaration for declaration in program.enums
        }
        self.variants: dict[str, tuple[str, EnumVariant]] = {}
        for declaration in program.enums:
            for variant in declaration.variants:
                self.variants.setdefault(variant.name, (declaration.name, variant))

        # İçe aktarılan struct'lar niteliksiz adlarıyla kullanılabilir; aynı adın
        # iki modülden gelmesi belirsizlik yaratacağı için reddedilir.
        for module in self.imports.values():
            for name, declaration in module.structs.items():
                existing = self.structs.get(name)
                if existing is not None and existing is not declaration:
                    raise SemanticError(
                        "KS1604",
                        f"'{name}' struct'ı hem bu dosyada hem de '{module.name}' "
                        "modülünde tanımlı. Adlardan birini değiştirin.",
                        declaration.location,
                    )
                self.structs.setdefault(name, declaration)
            for name, declaration in module.enums.items():
                existing = self.enums.get(name)
                if existing is not None and existing is not declaration:
                    raise SemanticError(
                        "KS1701",
                        f"'{name}' enum'u hem bu dosyada hem de '{module.name}' modülünde tanımlı.",
                        declaration.location,
                    )
                self.enums.setdefault(name, declaration)
                for variant in declaration.variants:
                    current = self.variants.get(variant.name)
                    if current is not None and current[1] is not variant:
                        raise SemanticError(
                            "KS1701",
                            f"'{variant.name}' varyantı modüller arasında çakışıyor.",
                            variant.location,
                        )
                    self.variants.setdefault(variant.name, (name, variant))
        self.scopes: list[dict[str, Symbol]] = []
        self.variable_count = 0
        self.capability_count = 0
        self.current_function: FunctionDeclaration | None = None

    def check(self) -> SemanticReport:
        seen_enum_names: set[str] = set()
        seen_variants: set[str] = set()
        for declaration in self.program.enums:
            if (
                declaration.name in seen_enum_names
                or declaration.name in self.structs
                or declaration.name in {"Option", "Result", "Error"}
            ):
                raise SemanticError(
                    "KS1701",
                    f"'{declaration.name}' enum adı birden fazla tanımlandı veya bir struct ile çakışıyor.",
                    declaration.location,
                )
            seen_enum_names.add(declaration.name)
            if not declaration.variants:
                raise SemanticError(
                    "KS1701",
                    f"'{declaration.name}' enum'u en az bir varyant içermelidir.",
                    declaration.location,
                )
            local_variants: set[str] = set()
            for variant in declaration.variants:
                if (
                    variant.name in local_variants
                    or variant.name in seen_variants
                    or variant.name in BUILTIN_CALLS
                    or variant.name in self.functions
                ):
                    raise SemanticError(
                        "KS1701",
                        f"'{variant.name}' varyantı birden fazla tanımlandı. Varyant adları program genelinde benzersizdir.",
                        variant.location,
                    )
                local_variants.add(variant.name)
                seen_variants.add(variant.name)
                if variant.payload_type is not None:
                    for type_name in variant.payload_type.names:
                        self._validate_generic_type(type_name, variant.location)
                    payload_names = set(variant.payload_type.names)
                    if self._types_are_sensitive(payload_names):
                        raise SemanticError(
                            "KS2402",
                            f"'{declaration.name}.{variant.name}' varyantı capability taşıyamaz.",
                            variant.location,
                        )

        for declaration in self.program.structs:
            seen: set[str] = set()
            for field in declaration.fields:
                if field.name in seen:
                    raise SemanticError(
                        "KS1501",
                        f"'{declaration.name}' struct'ında '{field.name}' alanı "
                        "birden fazla tanımlanmış.",
                        field.location,
                    )
                seen.add(field.name)
                for type_name in field.type_ref.names:
                    self._validate_generic_type(type_name, field.location)

                roots = set(field.type_ref.names) & ROOT_CAPABILITY_TYPES
                if roots:
                    raise SemanticError(
                        "KS2402",
                        f"'{declaration.name}.{field.name}' alanı kök capability "
                        f"taşıyamaz ({', '.join(sorted(roots))}). Kök yetki yalnızca "
                        "main içindeki SystemCaps'ten daraltılmalı; struct'a yalnızca "
                        "NetCaps / DiskCaps gibi daraltılmış jetonlar konabilir.",
                        field.location,
                    )

        for declaration in self.program.declarations:
            self._validate_function_signature(declaration)

        for declaration in self.program.declarations:
            self._check_function(declaration)

        return SemanticReport(
            functions=len(self.program.declarations),
            variables=self.variable_count,
            capability_values=self.capability_count,
        )

    def _validate_function_signature(self, function: FunctionDeclaration) -> None:
        if function.name in {"Some", "None", "Ok", "Err"} or function.name in self.variants:
            raise SemanticError(
                "KS1701",
                f"'{function.name}' adı bir enum constructor'ı ile çakışıyor.",
                function.location,
            )
        for parameter in function.parameters:
            for type_name in parameter.type_ref.names:
                self._validate_generic_type(type_name, parameter.location)
        if function.return_type is not None:
            for type_name in function.return_type.names:
                self._validate_generic_type(type_name, function.return_type.location)

        if function.name == "main":
            if len(function.parameters) > 1:
                raise SemanticError(
                    "KS1301",
                    "'main' sıfır parametre veya yalnızca bir SystemCaps parametresi "
                    "alabilir.",
                    function.location,
                )
            if (
                len(function.parameters) == 1
                and function.parameters[0].type_ref.names != ("SystemCaps",)
            ):
                parameter = function.parameters[0]
                raise SemanticError(
                    "KS2401",
                    "'main' tek parametre alıyorsa bu parametre tam olarak SystemCaps "
                    f"olmalıdır; {parameter.type_ref} bulundu. Runtime başka bir tipe "
                    "SystemCaps enjekte etmez.",
                    parameter.location,
                )

        for parameter in function.parameters:
            if (
                function.name == "main"
                and parameter.type_ref.names == ("SystemCaps",)
            ):
                continue
            roots = set(parameter.type_ref.names) & ROOT_CAPABILITY_TYPES
            if roots:
                raise SemanticError(
                    "KS2402",
                    f"'{function.name}' fonksiyonunun '{parameter.name}' parametresi "
                    f"kök capability taşıyamaz ({', '.join(sorted(roots))}). Kökü "
                    "main içinde daraltın ve yalnızca daraltılmış jetonu geçirin.",
                    parameter.location,
                )

        if function.return_type is not None:
            roots = set(function.return_type.names) & ROOT_CAPABILITY_TYPES
            if roots:
                raise SemanticError(
                    "KS2402",
                    f"'{function.name}' kök capability döndüremez "
                    f"({', '.join(sorted(roots))}). Kök yetkiler dolaşıma çıkamaz.",
                    function.return_type.location,
                )

    def _check_function(self, function: FunctionDeclaration) -> None:
        self.scopes.append({})
        previous_function = self.current_function
        self.current_function = function
        try:
            for parameter in function.parameters:
                type_name = str(parameter.type_ref)
                self._declare(
                    Symbol(
                        name=parameter.name,
                        type_name=type_name,
                        is_mutable=False,
                        location=parameter.location,
                    )
                )
            self._check_statements(function.body)
        finally:
            self.current_function = previous_function
            self.scopes.pop()

    def _check_block(self, block: Block) -> None:
        self.scopes.append({})
        try:
            self._check_statements(block)
        finally:
            self.scopes.pop()

    def _check_statements(self, block: Block) -> None:
        for statement in block.statements:
            self._check_statement(statement)

    def _check_statement(self, statement: Statement) -> None:
        if isinstance(statement, LetStatement):
            value_type = self._check_expression(statement.value)
            self._declare(
                Symbol(
                    name=statement.name,
                    type_name=value_type,
                    is_mutable=statement.is_mutable,
                    location=statement.location,
                )
            )
            self.variable_count += 1
            return

        if isinstance(statement, ReturnStatement):
            value_type = (
                "Void"
                if statement.value is None
                else self._check_expression(statement.value)
            )
            function = self.current_function
            if function is not None and function.return_type is not None:
                self._require_assignable(
                    function.return_type.names,
                    value_type,
                    f"'{function.name}' dönüş değeri",
                    statement.location,
                )
            return

        if isinstance(statement, ExpressionStatement):
            self._check_expression(statement.expression)
            if self._is_fallible_call(statement.expression):
                raise SemanticError(
                    "KS1401",
                    "Hata dönebilen çağrının sonucu ele alınmalıdır "
                    "('let ... = ...', 'or return', 'or varsayılan' "
                    "veya 'or { ... }' kullanın).",
                    statement.location,
                )
            return

        if isinstance(statement, IfStatement):
            condition_type = self._check_expression(statement.condition)
            self._require_bool(condition_type, "if koşulu", statement.location)
            self._check_block(statement.then_block)
            if isinstance(statement.else_branch, Block):
                self._check_block(statement.else_branch)
            elif isinstance(statement.else_branch, IfStatement):
                self._check_statement(statement.else_branch)
            return

        if isinstance(statement, WhileStatement):
            condition_type = self._check_expression(statement.condition)
            self._require_bool(condition_type, "while koşulu", statement.location)
            self._check_block(statement.body)
            return

        if isinstance(statement, ForStatement):
            iterable_type = self._check_expression(statement.iterable)
            if iterable_type is not None and iterable_type != "List":
                raise SemanticError(
                    "KS1301",
                    f"'for ... in' yalnızca List üzerinde çalışır, "
                    f"{iterable_type} bulundu.",
                    statement.location,
                )
            self.scopes.append({})
            try:
                self._declare(
                    Symbol(statement.variable, None, False, statement.location)
                )
                self.variable_count += 1
                self._check_statements(statement.body)
            finally:
                self.scopes.pop()
            return

        raise AssertionError(f"Desteklenmeyen statement: {type(statement).__name__}")

    def _check_expression(self, expression: Expression) -> str | None:
        if isinstance(expression, Literal):
            if isinstance(expression.value, bool):
                return "Bool"
            if isinstance(expression.value, str):
                return "String"
            if isinstance(expression.value, int):
                if not INT_MIN <= expression.value <= INT_MAX:
                    raise SemanticError(
                        "KS1302",
                        "Int literal işaretli 64-bit aralığın dışında: "
                        f"{expression.value}. Geçerli aralık {INT_MIN}..{INT_MAX}.",
                        expression.location,
                    )
                return "Int"
            if isinstance(expression.value, float):
                return "Float"
            return None

        if isinstance(expression, InterpolatedString):
            for part in expression.parts:
                self._check_expression(part)
                if self._is_fallible_call(part):
                    raise SemanticError(
                        "KS1401",
                        "İnterpolasyon içindeki hata dönebilen ifade önce 'or' ile "
                        "ele alınmalıdır.",
                        part.location,
                    )
            return "String"

        if isinstance(expression, ListLiteral):
            for item in expression.items:
                item_type = self._check_expression(item)
                if self._types_are_sensitive(self._type_names(item_type)):
                    raise SemanticError(
                        "KS2401",
                        "Capability taşıyan değerler List içine konamaz; öğe tipi "
                        "korunmadığı için bu işlem yetki type-laundering oluşturur.",
                        item.location,
                    )
            return "List"

        if isinstance(expression, MapLiteral):
            literal_keys: set[str] = set()
            for key, value in expression.entries:
                key_type = self._check_expression(key)
                if key_type is not None and key_type != "String":
                    raise SemanticError(
                        "KS1301",
                        f"Map anahtarı String olmalıdır, {key_type} bulundu.",
                        key.location,
                    )
                if isinstance(key, Literal) and isinstance(key.value, str):
                    if key.value in literal_keys:
                        raise SemanticError(
                            "KS1501",
                            f"Map literalinde '{key.value}' anahtarı birden fazla yazılmış.",
                            key.location,
                        )
                    literal_keys.add(key.value)

                value_type = self._check_expression(value)
                if self._types_are_sensitive(self._type_names(value_type)):
                    raise SemanticError(
                        "KS2401",
                        "Capability taşıyan değerler Map içine konamaz; Map.get() "
                        "öğe tipini statik olarak korumadığı için bu işlem yetki "
                        "type-laundering oluşturur.",
                        value.location,
                    )
            return "Map"

        if isinstance(expression, StructLiteral):
            return self._check_struct_literal(expression)

        if isinstance(expression, Identifier):
            symbol = self._resolve(expression.name)
            if symbol is not None:
                return symbol.type_name
            if expression.name in self.functions:
                function = self.functions[expression.name]
                return str(function.return_type) if function.return_type else "Void"
            if expression.name in self.imports:
                return MODULE_TYPE_PREFIX + expression.name
            variant = self.variants.get(expression.name)
            if variant is not None:
                return variant[0]
            if expression.name in BUILTIN_CALLS:
                return None
            self._raise_unknown_identifier(expression)

        if isinstance(expression, MemberExpression):
            object_type = self._check_expression(expression.object)

            if object_type == "SystemCaps" and expression.member in CAPABILITY_MEMBERS:
                self.capability_count += 1
                return CAPABILITY_MEMBERS[expression.member]

            if isinstance(object_type, str) and object_type.startswith(
                MODULE_TYPE_PREFIX
            ):
                module = self.imports[object_type[len(MODULE_TYPE_PREFIX):]]
                function = module.functions.get(expression.member)
                if function is not None:
                    return (
                        str(function.return_type) if function.return_type else "Void"
                    )
                if expression.member in module.structs:
                    return expression.member
                if expression.member in module.enums:
                    return expression.member
                raise SemanticError(
                    "KS1605",
                    f"'{module.name}' modülünde '{expression.member}' adında bir "
                    "fonksiyon veya struct yok.",
                    expression.location,
                )

            if object_type in CAPABILITY_TYPES:
                return None

            # Struct alan erişimi: alanın tipi döner, olmayan alan derlenmez.
            declaration = self.structs.get(object_type or "")
            if declaration is not None:
                for field in declaration.fields:
                    if field.name == expression.member:
                        return str(field.type_ref)
                raise SemanticError(
                    "KS1502",
                    f"'{object_type}' struct'ında '{expression.member}' adında bir "
                    "alan yok.",
                    expression.location,
                )

            return object_type

        if isinstance(expression, CallExpression):
            argument_types = [
                self._check_expression(argument)
                for argument in expression.arguments
            ]

            if isinstance(expression.callee, MemberExpression):
                receiver_type = self._check_expression(expression.callee.object)
                return self._check_method_call(
                    receiver_type,
                    expression.callee.member,
                    expression.location,
                    argument_types,
                    expression.arguments,
                )

            if isinstance(expression.callee, Identifier):
                name = expression.callee.name
                function = self.functions.get(name)
                if function is not None:
                    self._check_call_arguments(
                        function,
                        argument_types,
                        expression.location,
                    )
                    return (
                        str(function.return_type)
                        if function.return_type
                        else "Void"
                    )
                constructor = self.variants.get(name)
                if constructor is not None:
                    enum_name, variant = constructor
                    expected = 0 if variant.payload_type is None else 1
                    if len(argument_types) != expected:
                        raise SemanticError(
                            "KS1701",
                            f"'{name}' varyantı {expected} argüman bekler, {len(argument_types)} verildi.",
                            expression.location,
                        )
                    if variant.payload_type is not None:
                        self._require_assignable(
                            variant.payload_type.names,
                            argument_types[0],
                            f"'{name}' varyant payload'ı",
                            expression.location,
                        )
                    return enum_name
                if name == "Error":
                    if len(argument_types) != 1:
                        raise SemanticError("KS1301", "Error() 1 argüman bekler.", expression.location)
                    return "Error"
                if name == "Some":
                    if len(argument_types) != 1:
                        raise SemanticError("KS1701", "Some() 1 argüman bekler.", expression.location)
                    if self._types_are_sensitive(self._type_names(argument_types[0])):
                        raise SemanticError(
                            "KS2401",
                            "Capability taşıyan değerler Option payload'ına konamaz.",
                            expression.location,
                        )
                    return f"Option<{argument_types[0] or '_'}>"
                if name == "None":
                    if argument_types:
                        raise SemanticError("KS1701", "None() argüman almaz.", expression.location)
                    return "Option<_>"
                if name == "Ok":
                    if len(argument_types) != 1:
                        raise SemanticError("KS1701", "Ok() 1 argüman bekler.", expression.location)
                    if self._types_are_sensitive(self._type_names(argument_types[0])):
                        raise SemanticError(
                            "KS2401",
                            "Capability taşıyan değerler Result payload'ına konamaz.",
                            expression.location,
                        )
                    return f"Result<{argument_types[0] or '_'}, _>"
                if name == "Err":
                    if len(argument_types) != 1:
                        raise SemanticError("KS1701", "Err() 1 argüman bekler.", expression.location)
                    if self._types_are_sensitive(self._type_names(argument_types[0])):
                        raise SemanticError(
                            "KS2401",
                            "Capability taşıyan değerler Result payload'ına konamaz.",
                            expression.location,
                        )
                    return f"Result<_, {argument_types[0] or '_'}>"

            return self._check_expression(expression.callee)

        if isinstance(expression, BinaryExpression):
            return self._check_binary(expression)

        if isinstance(expression, UnaryExpression):
            if (
                expression.operator == "-"
                and isinstance(expression.operand, Literal)
                and isinstance(expression.operand.value, int)
                and not isinstance(expression.operand.value, bool)
            ):
                magnitude = expression.operand.value
                if magnitude == INT_MIN_MAGNITUDE:
                    return "Int"
                if magnitude > INT_MAX:
                    raise SemanticError(
                        "KS1302",
                        "Negatif Int literal işaretli 64-bit aralığın dışında: "
                        f"-{magnitude}. Geçerli alt sınır {INT_MIN}.",
                        expression.location,
                    )
            operand_type = self._check_expression(expression.operand)
            if expression.operator == "!":
                self._require_bool(operand_type, "'!' işleci", expression.location)
                return "Bool"
            if operand_type is not None and operand_type not in NUMERIC_TYPES:
                raise SemanticError(
                    "KS1301",
                    f"'-' işleci sayısal tip bekler, {operand_type} bulundu.",
                    expression.location,
                )
            return operand_type

        if isinstance(expression, OrReturnExpression):
            value_type = self._check_expression(expression.value)
            success_type = self._success_type(value_type)
            if expression.error is not None:
                error_type = self._check_expression(expression.error)
                if self.current_function is not None and self.current_function.return_type is not None:
                    self._require_assignable(
                        self.current_function.return_type.names,
                        error_type,
                        "'or return' hata değeri",
                        expression.error.location,
                    )
            return success_type

        if isinstance(expression, OrElseExpression):
            value_type = self._check_expression(expression.value)
            success_type = self._success_type(value_type)
            fallback_type = self._check_expression(expression.fallback)
            # Legacy `T or Error` akışında fallback tipinin T ile aynı olması
            # zorunlu değildir; bu davranış v0.7 programlarıyla uyumluluk için
            # korunur. Generic Option/Result ise aynı başarı tipine daralır.
            base, _ = self._generic_type(value_type or "")
            if base in {"Option", "Result"} and success_type is not None:
                self._require_assignable(
                    (success_type,),
                    fallback_type,
                    "'or' varsayılan değeri",
                    expression.fallback.location,
                )
                return self._unify_types(success_type, fallback_type, expression.location)
            return success_type or fallback_type

        if isinstance(expression, OrBlockExpression):
            value_type = self._check_expression(expression.value)
            self._check_block(expression.handler)
            return self._success_type(value_type)

        if isinstance(expression, MatchExpression):
            return self._check_match_expression(expression)

        if isinstance(expression, AssignmentExpression):
            value_type = self._check_expression(expression.value)
            if isinstance(expression.target, Identifier):
                symbol = self._resolve(expression.target.name)
                if symbol is None:
                    self._raise_unknown_identifier(expression.target)
                if not symbol.is_mutable:
                    raise SemanticError(
                        "KS1201",
                        f"'{symbol.name}' immutable bir değerdir; değiştirmek için 'let mut' kullanın.",
                        expression.location,
                    )
                if symbol.type_name is not None:
                    self._require_assignable(
                        (symbol.type_name,),
                        value_type,
                        f"'{symbol.name}' ataması",
                        expression.location,
                    )
                return symbol.type_name or value_type

            self._check_expression(expression.target)
            return value_type

        raise AssertionError(f"Desteklenmeyen expression: {type(expression).__name__}")

    def _check_struct_literal(self, expression: StructLiteral) -> str:
        declaration = self.structs.get(expression.type_name)
        if declaration is None:
            raise SemanticError(
                "KS1101",
                f"Tanımsız struct: '{expression.type_name}'.",
                expression.location,
            )

        expected = {field.name: field for field in declaration.fields}
        provided: set[str] = set()

        for name, value in expression.fields:
            if name not in expected:
                raise SemanticError(
                    "KS1501",
                    f"'{expression.type_name}' struct'ında '{name}' adında bir alan "
                    f"yok. Beklenen alanlar: {', '.join(sorted(expected))}.",
                    expression.location,
                )
            if name in provided:
                raise SemanticError(
                    "KS1501",
                    f"'{name}' alanı birden fazla kez verilmiş.",
                    expression.location,
                )

            value_type = self._check_expression(value)
            field = expected[name]
            self._require_assignable(
                field.type_ref.names,
                value_type,
                f"'{expression.type_name}.{name}' alanı",
                value.location,
            )
            provided.add(name)

        missing = set(expected) - provided
        if missing:
            raise SemanticError(
                "KS1501",
                f"'{expression.type_name}' struct'ında eksik alan(lar): "
                f"{', '.join(sorted(missing))}.",
                expression.location,
            )

        return expression.type_name

    def _check_binary(self, expression: BinaryExpression) -> str | None:
        left_type = self._check_expression(expression.left)
        right_type = self._check_expression(expression.right)
        operator = expression.operator

        if operator in LOGICAL_OPERATORS:
            self._require_bool(left_type, f"'{operator}' işlecinin sol tarafı", expression.location)
            self._require_bool(right_type, f"'{operator}' işlecinin sağ tarafı", expression.location)
            return "Bool"

        if operator in COMPARISON_OPERATORS:
            if (
                left_type is not None
                and right_type is not None
                and left_type != right_type
            ):
                raise SemanticError(
                    "KS1301",
                    f"'{operator}' iki farklı tipi karşılaştıramaz: {left_type} ve {right_type}.",
                    expression.location,
                )
            return "Bool"

        if operator in ARITHMETIC_OPERATORS:
            if left_type is not None and right_type is not None:
                if left_type != right_type:
                    raise SemanticError(
                        "KS1301",
                        f"'{operator}' iki farklı tipe uygulanamaz: {left_type} ve {right_type}.",
                        expression.location,
                    )
                if left_type == "String":
                    if operator != "+":
                        raise SemanticError(
                            "KS1301",
                            f"String yalnızca '+' ile birleştirilebilir; '{operator}' geçersiz.",
                            expression.location,
                        )
                    return "String"
                if left_type not in NUMERIC_TYPES:
                    raise SemanticError(
                        "KS1301",
                        f"'{operator}' işleci {left_type} tipine uygulanamaz.",
                        expression.location,
                    )
                return left_type
            return left_type or right_type

        return None

    def _validate_generic_type(
        self, type_name: str, location: SourceLocation
    ) -> None:
        base, arguments = self._generic_type(type_name)
        expected_arity = {"Option": 1, "Result": 2}.get(base)
        if arguments and expected_arity is None:
            raise SemanticError(
                "KS1301",
                f"'{base}' generic tip değildir; bu sürümde yalnızca Option<T> ve Result<T, E> desteklenir.",
                location,
            )
        if expected_arity is not None and len(arguments) != expected_arity:
            raise SemanticError(
                "KS1301",
                f"{base} {expected_arity} tip argümanı bekler, {len(arguments)} verildi.",
                location,
            )
        for argument in arguments:
            self._validate_generic_type(argument, location)

    @staticmethod
    def _split_top_level(text: str, separator: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        start = 0
        index = 0
        while index <= len(text) - len(separator):
            char = text[index]
            if char == "<":
                depth += 1
            elif char == ">":
                depth -= 1
            if depth == 0 and text.startswith(separator, index):
                parts.append(text[start:index].strip())
                index += len(separator)
                start = index
                continue
            index += 1
        parts.append(text[start:].strip())
        return [part for part in parts if part]

    @classmethod
    def _generic_type(cls, name: str) -> tuple[str, tuple[str, ...]]:
        name = name.strip()
        if "<" not in name or not name.endswith(">"):
            return name, ()
        base, rest = name.split("<", 1)
        inner = rest[:-1]
        return base.strip(), tuple(cls._split_top_level(inner, ","))

    def _type_names(self, type_name: str | None) -> set[str]:
        if type_name is None:
            return set()
        return set(self._split_top_level(type_name, " or "))

    def _type_compatible(self, expected: str, actual: str) -> bool:
        if expected == actual or expected == "_" or actual == "_":
            return True
        expected_base, expected_args = self._generic_type(expected)
        actual_base, actual_args = self._generic_type(actual)
        if expected_base != actual_base or len(expected_args) != len(actual_args):
            return False
        if not expected_args:
            return False
        return all(
            self._type_compatible(expected_arg, actual_arg)
            for expected_arg, actual_arg in zip(expected_args, actual_args)
        )

    def _unify_types(
        self,
        left: str | None,
        right: str | None,
        location: SourceLocation,
    ) -> str | None:
        if left is None:
            return right
        if right is None:
            return left
        if left == right:
            return left
        left_base, left_args = self._generic_type(left)
        right_base, right_args = self._generic_type(right)
        if left_base == right_base and left_args and len(left_args) == len(right_args):
            merged: list[str] = []
            for left_arg, right_arg in zip(left_args, right_args):
                if left_arg == "_":
                    merged.append(right_arg)
                elif right_arg == "_":
                    merged.append(left_arg)
                elif left_arg == right_arg:
                    merged.append(left_arg)
                else:
                    raise SemanticError(
                        "KS1702",
                        f"match kolları uyumsuz tip döndürüyor: {left} ve {right}.",
                        location,
                    )
            return f"{left_base}<{', '.join(merged)}>"
        if self._type_compatible(left, right):
            return left
        if self._type_compatible(right, left):
            return right
        raise SemanticError(
            "KS1702",
            f"match kolları uyumsuz tip döndürüyor: {left} ve {right}.",
            location,
        )

    def _success_type(self, type_name: str | None) -> str | None:
        names = self._type_names(type_name)
        if "Error" in names:
            remaining = sorted(names - {"Error"})
            return " or ".join(remaining) if remaining else None
        if type_name is None:
            return None
        base, arguments = self._generic_type(type_name)
        if base == "Option" and len(arguments) == 1:
            return arguments[0]
        if base == "Result" and len(arguments) == 2:
            return arguments[0]
        return type_name

    def _enum_shape(self, type_name: str | None) -> dict[str, str | None] | None:
        if type_name is None or len(self._type_names(type_name)) != 1:
            return None
        base, arguments = self._generic_type(type_name)
        if base == "Option" and len(arguments) == 1:
            return {"Some": arguments[0], "None": None}
        if base == "Result" and len(arguments) == 2:
            return {"Ok": arguments[0], "Err": arguments[1]}
        declaration = self.enums.get(type_name)
        if declaration is None:
            return None
        return {
            variant.name: (
                str(variant.payload_type) if variant.payload_type is not None else None
            )
            for variant in declaration.variants
        }

    def _check_match_expression(self, expression: MatchExpression) -> str | None:
        value_type = self._check_expression(expression.value)
        variants = self._enum_shape(value_type)
        if variants is None:
            raise SemanticError(
                "KS1702",
                f"match bir enum, Option veya Result bekler; {value_type or '<bilinmiyor>'} bulundu.",
                expression.location,
            )
        seen: set[str] = set()
        result_type: str | None = None
        for arm in expression.arms:
            if arm.variant in seen:
                raise SemanticError(
                    "KS1702",
                    f"match içinde '{arm.variant}' kolu birden fazla yazılmış.",
                    arm.location,
                )
            seen.add(arm.variant)
            if arm.variant not in variants:
                raise SemanticError(
                    "KS1702",
                    f"'{arm.variant}' varyantı {value_type} tipine ait değil.",
                    arm.location,
                )
            payload_type = variants[arm.variant]
            if payload_type is None and arm.binding is not None:
                raise SemanticError(
                    "KS1702",
                    f"'{arm.variant}' payload taşımadığı için bağlama alamaz.",
                    arm.location,
                )
            if payload_type is not None and arm.binding is None:
                raise SemanticError(
                    "KS1702",
                    f"'{arm.variant}' payload taşıdığı için bir bağlama adı gerektirir.",
                    arm.location,
                )
            self.scopes.append({})
            try:
                if arm.binding is not None:
                    self._declare(Symbol(arm.binding, payload_type, False, arm.location))
                arm_type = self._check_expression(arm.body)
            finally:
                self.scopes.pop()
            result_type = self._unify_types(result_type, arm_type, arm.location)
        missing = set(variants) - seen
        if missing:
            raise SemanticError(
                "KS1702",
                "match exhaustive olmalıdır; eksik varyantlar: "
                + ", ".join(sorted(missing))
                + ".",
                expression.location,
            )
        return result_type

    def _name_is_sensitive(
        self,
        name: str,
        seen: set[str] | None = None,
    ) -> bool:
        if name in CAPABILITY_TYPES:
            return True
        base, arguments = self._generic_type(name)
        if arguments and any(self._name_is_sensitive(argument, seen) for argument in arguments):
            return True
        declaration = self.structs.get(base)
        if declaration is None:
            enum_declaration = self.enums.get(base)
            if enum_declaration is None:
                return False
            visited = set(seen or ())
            if base in visited:
                return False
            visited.add(base)
            return any(
                variant.payload_type is not None
                and any(self._name_is_sensitive(type_name, visited) for type_name in variant.payload_type.names)
                for variant in enum_declaration.variants
            )
        visited = set(seen or ())
        if base in visited:
            return False
        visited.add(base)
        return any(
            self._name_is_sensitive(type_name, visited)
            for field in declaration.fields
            for type_name in field.type_ref.names
        )

    def _types_are_sensitive(self, names: set[str]) -> bool:
        return any(self._name_is_sensitive(name) for name in names)

    def _require_assignable(
        self,
        expected_names,
        actual_type: str | None,
        subject: str,
        location: SourceLocation,
    ) -> None:
        expected = set(expected_names)
        actual = self._type_names(actual_type)
        expected_sensitive = self._types_are_sensitive(expected)
        actual_sensitive = self._types_are_sensitive(actual)

        if not actual:
            if expected_sensitive:
                raise SemanticError(
                    "KS2401",
                    f"{subject} capability taşıyan {', '.join(sorted(expected))} "
                    "tipini bekliyor; verilen değerin tipi güvenli biçimde "
                    "kanıtlanamadı. Capability type-laundering reddedildi.",
                    location,
                )
            return

        if all(
            any(self._type_compatible(expected_name, actual_name) for expected_name in expected)
            for actual_name in actual
        ):
            return

        code = "KS2401" if expected_sensitive or actual_sensitive else "KS1301"
        expected_text = " or ".join(sorted(expected)) or "<bilinmiyor>"
        actual_text = " or ".join(sorted(actual))
        detail = (
            " Capability değerleri başka bir tip gibi gösterilemez."
            if code == "KS2401"
            else ""
        )
        raise SemanticError(
            code,
            f"{subject} {expected_text} bekler, {actual_text} bulundu.{detail}",
            location,
        )

    def _check_call_arguments(
        self,
        function: FunctionDeclaration,
        argument_types: list[str | None],
        location: SourceLocation,
    ) -> None:
        parameters = function.parameters
        if len(argument_types) != len(parameters):
            missing = parameters[len(argument_types):]
            missing_sensitive = [
                parameter
                for parameter in missing
                if any(
                    self._name_is_sensitive(type_name)
                    for type_name in parameter.type_ref.names
                )
            ]
            if missing_sensitive:
                required = ", ".join(
                    f"{parameter.name}: {parameter.type_ref}"
                    for parameter in missing_sensitive
                )
                raise SemanticError(
                    "KS2401",
                    f"'{function.name}' çağrısı gerekli capability taşıyan "
                    f"değeri almadı: {required}.",
                    location,
                )
            raise SemanticError(
                "KS1301",
                f"'{function.name}' çağrısı {len(parameters)} argüman bekler, "
                f"{len(argument_types)} verildi.",
                location,
            )

        for index, (parameter, actual_type) in enumerate(
            zip(parameters, argument_types),
            start=1,
        ):
            self._require_assignable(
                parameter.type_ref.names,
                actual_type,
                f"'{function.name}' çağrısının {index}. argümanı",
                location,
            )

    def _check_net_origin(
        self,
        arguments: list[Expression],
        location: SourceLocation,
    ) -> None:
        """Sabit ağ origin'lerini derleme anında HTTP(S) ile sınırlar.

        Dinamik origin ifadeleri burada tahmin edilmez; runtime aynı kuralı
        _origin_key içinde fail-closed olarak yeniden uygular.
        """
        if not arguments:
            return
        origin = arguments[0]
        if not isinstance(origin, Literal) or not isinstance(origin.value, str):
            return
        try:
            parsed = urlsplit(origin.value)
            scheme = parsed.scheme.lower()
            hostname = parsed.hostname
        except ValueError:
            scheme = ""
            hostname = None
        if scheme not in NET_ORIGIN_SCHEMES or hostname is None:
            raise SemanticError(
                "KS2405",
                "NetRoot.allow origin'i yalnızca mutlak http:// veya https:// "
                f"olabilir; {origin.value!r} reddedildi.",
                location,
            )

    def _check_method_call(
        self,
        receiver_type: str | None,
        method_name: str,
        location: SourceLocation,
        argument_types: list[str | None] | None = None,
        arguments: list[Expression] | None = None,
    ) -> str | None:
        # List metotları yetki denetiminden ÖNCE ele alınır: 'get' aynı zamanda
        # bir yetki metodu adıdır ve liste erişimi yanlışlıkla yetki ihlali
        # sayılmamalıdır.
        if isinstance(receiver_type, str) and receiver_type.startswith(
            MODULE_TYPE_PREFIX
        ):
            module = self.imports[receiver_type[len(MODULE_TYPE_PREFIX):]]
            function = module.functions.get(method_name)
            if function is None:
                raise SemanticError(
                    "KS1605",
                    f"'{module.name}' modülünde '{method_name}' adında bir fonksiyon "
                    "yok.",
                    location,
                )
            self._check_call_arguments(function, argument_types or [], location)
            return str(function.return_type) if function.return_type else "Void"

        if receiver_type == "String":
            expected_arity = {
                "length": 0,
                "to_int": 0,
                "to_float": 0,
                "contains": 1,
                "trim": 0,
                "split": 1,
                "join": 1,
            }
            if method_name not in STRING_METHODS:
                raise SemanticError(
                    "KS1502",
                    f"String üzerinde '{method_name}' metodu yok. "
                    f"Kullanılabilir: {', '.join(sorted(STRING_METHODS))}.",
                    location,
                )
            values = argument_types or []
            required = expected_arity[method_name]
            if len(values) != required:
                raise SemanticError(
                    "KS1301",
                    f"String.{method_name}() {required} argüman bekler, "
                    f"{len(values)} verildi.",
                    location,
                )
            if method_name == "split":
                self._require_assignable(
                    ("String",),
                    values[0],
                    "String.split() ayıracı",
                    location,
                )
                return "List"
            if method_name == "join":
                self._require_assignable(
                    ("List",),
                    values[0],
                    "String.join() parçaları",
                    location,
                )
                return "String"
            return {
                "length": "Int",
                "to_int": "Int",
                "to_float": "Float",
                "contains": "Bool",
                "trim": "String",
            }[method_name]

        if receiver_type == "List":
            expected_arity = {
                "length": 0,
                "get": 1,
                "push": 1,
                "contains": 1,
                "sort": 0,
                "filter": 1,
            }
            if method_name not in LIST_METHODS:
                raise SemanticError(
                    "KS1502",
                    f"List üzerinde '{method_name}' metodu yok. "
                    f"Kullanılabilir: {', '.join(sorted(LIST_METHODS))}.",
                    location,
                )
            values = argument_types or []
            required = expected_arity[method_name]
            if len(values) != required:
                raise SemanticError(
                    "KS1301",
                    f"List.{method_name}() {required} argüman bekler, "
                    f"{len(values)} verildi.",
                    location,
                )
            if method_name == "get":
                self._require_assignable(("Int",), values[0], "List.get() indeksi", location)
                return None
            if method_name == "push":
                if self._types_are_sensitive(self._type_names(values[0])):
                    raise SemanticError(
                        "KS2401",
                        "Capability taşıyan değerler List içine konamaz.",
                        location,
                    )
                return "List"
            if method_name == "filter":
                predicate = (arguments or [None])[0]
                if not isinstance(predicate, Identifier) or predicate.name not in self.functions:
                    raise SemanticError(
                        "KS1301",
                        "List.filter() yerel, adlandırılmış bir predicate fonksiyonu bekler.",
                        location,
                    )
                function = self.functions[predicate.name]
                if len(function.parameters) != 1:
                    raise SemanticError(
                        "KS1301",
                        f"List.filter() predicate'i 1 argüman almalıdır; "
                        f"'{function.name}' {len(function.parameters)} argüman alıyor.",
                        location,
                    )
                if function.return_type is None or function.return_type.names != ("Bool",):
                    raise SemanticError(
                        "KS1301",
                        "List.filter() predicate'i Bool döndürmelidir.",
                        location,
                    )
                return "List"
            return {
                "length": "Int",
                "contains": "Bool",
                "sort": "List",
            }.get(method_name)

        if receiver_type == "Map":
            expected_arity = {
                "get": 1,
                "set": 2,
                "keys": 0,
                "contains": 1,
            }
            if method_name not in MAP_METHODS:
                raise SemanticError(
                    "KS1502",
                    f"Map üzerinde '{method_name}' metodu yok. "
                    f"Kullanılabilir: {', '.join(sorted(MAP_METHODS))}.",
                    location,
                )

            arguments = argument_types or []
            required = expected_arity[method_name]
            if len(arguments) != required:
                raise SemanticError(
                    "KS1301",
                    f"Map.{method_name}() {required} argüman bekler, "
                    f"{len(arguments)} verildi.",
                    location,
                )
            if method_name in {"get", "set", "contains"}:
                key_type = arguments[0]
                if key_type is not None and key_type != "String":
                    raise SemanticError(
                        "KS1301",
                        f"Map.{method_name}() anahtarı String olmalıdır, "
                        f"{key_type} bulundu.",
                        location,
                    )
            if method_name == "set":
                value_type = arguments[1]
                if self._types_are_sensitive(self._type_names(value_type)):
                    raise SemanticError(
                        "KS2401",
                        "Capability taşıyan değerler Map içine konamaz.",
                        location,
                    )
                return "Map"
            if method_name == "keys":
                return "List"
            if method_name == "contains":
                return "Bool"
            return None

        if receiver_type in self.structs:
            raise SemanticError(
                "KS1502",
                f"'{receiver_type}' struct'ında '{method_name}' adında bir metot yok.",
                location,
            )

        if receiver_type in ROOT_METHODS:
            mapping = ROOT_METHODS[receiver_type]
            if method_name in mapping:
                if receiver_type == "NetRoot" and method_name == "allow":
                    self._check_net_origin(arguments or [], location)
                self.capability_count += 1
                return mapping[method_name]
            raise SemanticError(
                "KS2402",
                f"{receiver_type} kök yetkisi doğrudan '{method_name}' yapamaz; "
                f"önce {' veya '.join(sorted(mapping))} ile daraltın.",
                location,
            )

        if receiver_type in NARROWED_METHODS:
            if method_name in NARROWING_METHODS:
                raise SemanticError(
                    "KS2403",
                    f"{receiver_type} daraltılmış bir yetkidir; '{method_name}' ile "
                    "yeniden genişletilemez. Yeni kapsam için kök yetkiden türetin.",
                    location,
                )
            if method_name in NARROWED_METHODS[receiver_type]:
                return None
            raise SemanticError(
                "KS2404",
                f"{receiver_type} yetkisi '{method_name}' işlemine izin vermez.",
                location,
            )

        if receiver_type == "SystemCaps":
            raise SemanticError(
                "KS2402",
                "SystemCaps üzerinde doğrudan işlem yapılamaz; "
                "caps.net / caps.disk gibi kök yetkilerden daraltın.",
                location,
            )

        if method_name in GUARDED_METHODS:
            raise SemanticError(
                "KS2401",
                f"'{method_name}' işlemi için gerekli yetki bu scope içinde mevcut değil.",
                location,
            )

        return None

    def _is_fallible_call(self, expression: Expression) -> bool:
        if not isinstance(expression, CallExpression):
            return False

        callee = expression.callee
        if isinstance(callee, Identifier):
            if callee.name == "Error":
                return True
            function = self.functions.get(callee.name)
            if function is None or function.return_type is None:
                return False
            return_type = str(function.return_type)
            base, _ = self._generic_type(return_type)
            return "Error" in function.return_type.names or base in {"Option", "Result"}

        if isinstance(callee, MemberExpression):
            receiver = self._receiver_type(callee.object)
            if isinstance(receiver, str) and receiver.startswith(MODULE_TYPE_PREFIX):
                module = self.imports.get(receiver[len(MODULE_TYPE_PREFIX):])
                function = module.functions.get(callee.member) if module else None
                if function is None or function.return_type is None:
                    return False
                return_type = str(function.return_type)
                base, _ = self._generic_type(return_type)
                return "Error" in function.return_type.names or base in {"Option", "Result"}
            if receiver == "String" and callee.member in {
                "to_int",
                "to_float",
                "split",
                "join",
            }:
                return True
            if receiver == "List" and callee.member in {"get", "sort", "filter"}:
                return True
            if receiver == "Map" and callee.member == "get":
                return True
            return receiver in NARROWED_METHODS

        return False

    def _receiver_type(self, expression: Expression) -> str | None:
        if isinstance(expression, Literal):
            if isinstance(expression.value, bool):
                return "Bool"
            if isinstance(expression.value, str):
                return "String"
            if isinstance(expression.value, int):
                return "Int"
            if isinstance(expression.value, float):
                return "Float"
            return None
        if isinstance(expression, InterpolatedString):
            return "String"
        if isinstance(expression, ListLiteral):
            return "List"
        if isinstance(expression, MapLiteral):
            return "Map"
        if isinstance(expression, StructLiteral):
            return expression.type_name
        if isinstance(expression, MatchExpression):
            return self._check_match_expression(expression)
        if isinstance(expression, Identifier):
            symbol = self._resolve(expression.name)
            if symbol is not None:
                return symbol.type_name
            if expression.name in self.imports:
                return MODULE_TYPE_PREFIX + expression.name
            return None
        if isinstance(expression, MemberExpression):
            object_type = self._receiver_type(expression.object)
            if object_type == "SystemCaps" and expression.member in CAPABILITY_MEMBERS:
                return CAPABILITY_MEMBERS[expression.member]
            return None
        if isinstance(expression, CallExpression):
            callee = expression.callee
            if isinstance(callee, Identifier):
                function = self.functions.get(callee.name)
                if function is not None and function.return_type is not None:
                    return str(function.return_type)
                return None
            if isinstance(callee, MemberExpression):
                receiver = self._receiver_type(callee.object)
                if receiver == "String":
                    return {
                        "length": "Int",
                        "to_int": "Int",
                        "to_float": "Float",
                        "contains": "Bool",
                        "trim": "String",
                        "split": "List",
                        "join": "String",
                    }.get(callee.member)
                if receiver == "List":
                    return {
                        "length": "Int",
                        "push": "List",
                        "contains": "Bool",
                        "sort": "List",
                        "filter": "List",
                    }.get(callee.member)
                if receiver == "Map":
                    return {
                        "set": "Map",
                        "keys": "List",
                        "contains": "Bool",
                    }.get(callee.member)
            return None
        return None

    def _require_bool(
        self, type_name: str | None, subject: str, location: SourceLocation
    ) -> None:
        if type_name is not None and type_name != "Bool":
            raise SemanticError(
                "KS1301",
                f"{subject} Bool olmalıdır, {type_name} bulundu.",
                location,
            )

    def _declare(self, symbol: Symbol) -> None:
        scope = self.scopes[-1]
        if symbol.name in scope:
            raise SemanticError(
                "KS1102",
                f"'{symbol.name}' bu scope içinde zaten tanımlı.",
                symbol.location,
            )
        scope[symbol.name] = symbol
        if symbol.type_name in CAPABILITY_TYPES:
            self.capability_count += 1

    def _resolve(self, name: str) -> Symbol | None:
        for scope in reversed(self.scopes):
            symbol = scope.get(name)
            if symbol is not None:
                return symbol
        return None

    def _raise_unknown_identifier(self, identifier: Identifier) -> None:
        if identifier.name in CAPABILITY_MEMBERS:
            required = CAPABILITY_MEMBERS[identifier.name]
            raise SemanticError(
                "KS2401",
                f"{required} yetkisi bu scope içinde mevcut değil.",
                identifier.location,
            )
        raise SemanticError(
            "KS1101",
            f"Tanımsız isim: '{identifier.name}'.",
            identifier.location,
        )


def check(
    program: Program, imports: dict[str, ImportedModule] | None = None
) -> SemanticReport:
    return SemanticChecker(program, imports).check()
