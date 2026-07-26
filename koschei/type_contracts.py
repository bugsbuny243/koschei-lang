"""Structural type contracts and generic-call inference for V5 Typed HIR."""

from __future__ import annotations

from .ast_nodes import SourceLocation
from .semantic import CAPABILITY_TYPES, ImportedModule, SemanticError
from .type_system import (
    STRING,
    GenericType,
    NamedType,
    TypeNode,
    TypeVariable,
    UnionType,
    UnknownType,
    alternatives,
    bind_type_variables,
    parse_type_ref,
    render_type,
    substitute_type,
    unresolved_type_variables,
)

GENERIC_ARITY = {"Option": 1, "Result": 2, "List": 1, "Map": 2}
COLLECTION_NAMES = {"List", "Map"}
CONTAINER_NAMES = {"Option", "Result", "List", "Map"}
RESERVED_TYPE_PARAMETERS = {
    "Int",
    "Float",
    "String",
    "Bool",
    "Void",
    "Error",
    "Option",
    "Result",
    "List",
    "Map",
    *CAPABILITY_TYPES,
}


def is_assignable(expected: TypeNode, actual: TypeNode) -> bool:
    """Return whether every possible actual value satisfies expected."""

    if isinstance(expected, UnknownType) or isinstance(actual, UnknownType):
        return True
    if isinstance(actual, UnionType):
        return all(is_assignable(expected, option) for option in actual.options)
    if isinstance(expected, UnionType):
        return all(
            any(is_assignable(option, actual_item) for option in expected.options)
            for actual_item in alternatives(actual)
        )
    if expected == actual:
        return True
    if isinstance(expected, TypeVariable) or isinstance(actual, TypeVariable):
        return False
    if isinstance(expected, NamedType) and isinstance(actual, GenericType):
        return expected.name in COLLECTION_NAMES and expected.name == actual.name
    if isinstance(expected, GenericType) and isinstance(actual, NamedType):
        return actual.name in COLLECTION_NAMES and expected.name == actual.name
    if isinstance(expected, GenericType) and isinstance(actual, GenericType):
        return (
            expected.name == actual.name
            and len(expected.arguments) == len(actual.arguments)
            and all(
                is_assignable(expected_item, actual_item)
                for expected_item, actual_item in zip(
                    expected.arguments, actual.arguments
                )
            )
        )
    return False


def require_assignable(
    expected: TypeNode,
    actual: TypeNode,
    subject: str,
    location: SourceLocation,
) -> None:
    if not is_assignable(expected, actual):
        raise SemanticError(
            "KS1301",
            f"{subject} {render_type(expected)} bekler, "
            f"{render_type(actual)} bulundu.",
            location,
        )


def function_type(function, type_ref) -> TypeNode:
    return bind_type_variables(
        parse_type_ref(type_ref), frozenset(function.type_parameters)
    )


def _same_inference(left: TypeNode, right: TypeNode) -> bool:
    return is_assignable(left, right) and is_assignable(right, left)


def _infer_pattern(
    pattern: TypeNode,
    actual: TypeNode,
    mapping: dict[str, TypeNode],
    subject: str,
    location: SourceLocation,
) -> None:
    if isinstance(pattern, TypeVariable):
        if isinstance(actual, UnknownType):
            return
        previous = mapping.get(pattern.name)
        if previous is None:
            mapping[pattern.name] = actual
            return
        if not _same_inference(previous, actual):
            raise SemanticError(
                "KS1307",
                f"{subject}: '{pattern.name}' için hem {render_type(previous)} "
                f"hem {render_type(actual)} çıkarıldı.",
                location,
            )
        return

    if isinstance(pattern, GenericType) and isinstance(actual, GenericType):
        if pattern.name != actual.name or len(pattern.arguments) != len(actual.arguments):
            return
        for expected_item, actual_item in zip(pattern.arguments, actual.arguments):
            _infer_pattern(expected_item, actual_item, mapping, subject, location)
        return

    if isinstance(pattern, UnionType):
        candidates = [
            option for option in pattern.options if is_assignable(option, actual)
        ]
        if len(candidates) == 1:
            _infer_pattern(candidates[0], actual, mapping, subject, location)


def infer_function_mapping(
    function,
    arguments: tuple[TypeNode, ...],
    location: SourceLocation,
) -> dict[str, TypeNode]:
    if len(arguments) != len(function.parameters):
        raise SemanticError(
            "KS1301",
            f"'{function.name}' {len(function.parameters)} argüman bekler, "
            f"{len(arguments)} verildi.",
            location,
        )

    mapping: dict[str, TypeNode] = {}
    for index, (parameter, actual) in enumerate(
        zip(function.parameters, arguments), start=1
    ):
        pattern = function_type(function, parameter.type_ref)
        _infer_pattern(
            pattern,
            actual,
            mapping,
            f"'{function.name}' çağrısının {index}. argümanı",
            location,
        )
    return mapping


def instantiate_function(
    function,
    arguments: tuple[TypeNode, ...],
    location: SourceLocation,
    validator: "TypeContractValidator",
) -> TypeNode:
    """Infer a generic call and return its fully substituted result type."""

    mapping = infer_function_mapping(function, arguments, location)
    missing = [name for name in function.type_parameters if name not in mapping]
    if missing:
        raise SemanticError(
            "KS1307",
            f"'{function.name}' çağrısında şu tip parametreleri çıkarılamadı: "
            + ", ".join(missing)
            + ". Tip parametresini en az bir giriş parametresinde kullanın.",
            location,
        )

    for name, actual in mapping.items():
        if validator.is_sensitive(actual):
            raise SemanticError(
                "KS2402",
                f"'{function.name}' generic çağrısında {name} capability taşıyan "
                f"{render_type(actual)} olamaz. Capability generics henüz kapalıdır.",
                location,
            )

    for index, (parameter, actual) in enumerate(
        zip(function.parameters, arguments), start=1
    ):
        expected = substitute_type(function_type(function, parameter.type_ref), mapping)
        require_assignable(
            expected,
            actual,
            f"'{function.name}' çağrısının {index}. argümanı",
            location,
        )
        validator.validate_type(expected, location, f"'{function.name}' parametresi")

    result = substitute_type(function_type(function, function.return_type), mapping)
    unresolved = unresolved_type_variables(result)
    if unresolved:
        raise SemanticError(
            "KS1307",
            f"'{function.name}' dönüş tipinde çözülemeyen tip parametresi: "
            + ", ".join(sorted(unresolved)),
            location,
        )
    validator.validate_type(result, location, f"'{function.name}' dönüş tipi")
    return result


class TypeContractValidator:
    def __init__(self, program, imports: dict[str, ImportedModule] | None = None) -> None:
        self.program = program
        self.imports = imports or {}
        self.structs = {item.name: item for item in program.structs}
        self.enums = {item.name: item for item in program.enums}
        for module in self.imports.values():
            self.structs.update(module.structs)
            self.enums.update(module.enums)

    def validate(self) -> None:
        for declaration in self.program.structs:
            for field in declaration.fields:
                self.validate_type(
                    parse_type_ref(field.type_ref),
                    field.location,
                    f"'{declaration.name}.{field.name}' alanı",
                )
        for declaration in self.program.enums:
            for variant in declaration.variants:
                if variant.payload_type is not None:
                    self.validate_type(
                        parse_type_ref(variant.payload_type),
                        variant.location,
                        f"'{declaration.name}.{variant.name}' payload'u",
                    )
        for function in self.program.declarations:
            self.validate_function(function)

    def validate_function(self, function) -> None:
        seen: set[str] = set()
        for name in function.type_parameters:
            if name in seen:
                raise SemanticError(
                    "KS1307",
                    f"'{function.name}' içinde '{name}' tip parametresi birden fazla tanımlandı.",
                    function.location,
                )
            if name in RESERVED_TYPE_PARAMETERS:
                raise SemanticError(
                    "KS1307",
                    f"'{name}' yerleşik veya capability tipi olduğu için tip parametresi olamaz.",
                    function.location,
                )
            seen.add(name)
        if function.name == "main" and function.type_parameters:
            raise SemanticError(
                "KS1307",
                "'main' generic olamaz; runtime giriş tiplerini çıkaramaz.",
                function.location,
            )
        for parameter in function.parameters:
            self.validate_type(
                function_type(function, parameter.type_ref),
                parameter.location,
                f"'{function.name}.{parameter.name}' parametresi",
            )
        if function.return_type is not None:
            self.validate_type(
                function_type(function, function.return_type),
                function.return_type.location,
                f"'{function.name}' dönüş tipi",
            )

    def validate_type(
        self, type_node: TypeNode, location: SourceLocation, subject: str
    ) -> None:
        if isinstance(type_node, (UnknownType, TypeVariable)):
            return
        if isinstance(type_node, UnionType):
            for option in type_node.options:
                self.validate_type(option, location, subject)
            return
        if isinstance(type_node, NamedType):
            return
        expected = GENERIC_ARITY.get(type_node.name)
        if expected is None:
            raise SemanticError(
                "KS1301",
                f"{subject}: '{type_node.name}' kullanıcı tanımlı generic tip "
                "değildir. Bu dilimde Option, Result, List ve Map desteklenir.",
                location,
            )
        if len(type_node.arguments) != expected:
            raise SemanticError(
                "KS1301",
                f"{subject}: {type_node.name} {expected} tip argümanı bekler, "
                f"{len(type_node.arguments)} verildi.",
                location,
            )
        if type_node.name == "Map" and type_node.arguments[0] != STRING:
            raise SemanticError(
                "KS1301",
                f"{subject}: Map anahtar tipi String olmalıdır, "
                f"{render_type(type_node.arguments[0])} bulundu.",
                location,
            )
        for argument in type_node.arguments:
            self.validate_type(argument, location, subject)
        if type_node.name in CONTAINER_NAMES and any(
            self.is_sensitive(argument) for argument in type_node.arguments
        ):
            raise SemanticError(
                "KS2402",
                f"{subject}: capability değeri {type_node.name} içinde "
                "gizlenemez.",
                location,
            )

    def is_sensitive(self, type_node: TypeNode, seen: set[str] | None = None) -> bool:
        seen = set() if seen is None else seen
        if isinstance(type_node, (UnknownType, TypeVariable)):
            return False
        if isinstance(type_node, UnionType):
            return any(self.is_sensitive(option, seen) for option in type_node.options)
        if isinstance(type_node, GenericType):
            return any(
                self.is_sensitive(argument, seen)
                for argument in type_node.arguments
            )
        if type_node.name in CAPABILITY_TYPES:
            return True
        if type_node.name in seen:
            return False
        nested_seen = seen | {type_node.name}
        declaration = self.structs.get(type_node.name)
        if declaration is not None:
            return any(
                self.is_sensitive(parse_type_ref(field.type_ref), nested_seen)
                for field in declaration.fields
            )
        enum = self.enums.get(type_node.name)
        if enum is not None:
            return any(
                variant.payload_type is not None
                and self.is_sensitive(
                    parse_type_ref(variant.payload_type), nested_seen
                )
                for variant in enum.variants
            )
        return False


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    CATALOG.setdefault(
        "KS1307",
        Diagnostic(
            "KS1307",
            "Generic tip çıkarımı başarısız",
            "Generic fonksiyonun bir tip parametresi çağrıdan güvenli ve tek anlamlı biçimde çıkarılamadı.",
            "Koschei gizli dinamik tipe düşmez. Aynı T için çelişen tipler veya yalnız dönüşte kullanılan T backend ayrışması üretir.",
            "Tip parametresini giriş parametrelerinde kullanın ve aynı tip parametresine verilen değerleri aynı yapısal tipte tutun.",
            "fn first<T>(items: List<T>) -> Option<T> { return items.get(0) }",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS1307",
        Diagnostic(
            "KS1307",
            "Generic type inference failed",
            "A generic function type parameter could not be inferred safely and unambiguously from the call.",
            "Koschei does not fall back to hidden dynamic typing. Conflicting evidence for T or a T used only in the result would diverge across backends.",
            "Use each type parameter in an input position and pass structurally consistent values for repeated parameters.",
            "fn first<T>(items: List<T>) -> Option<T> { return items.get(0) }",
        ),
    )


_register_diagnostics()
