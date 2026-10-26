"""Structural type contracts and generic inference for V5 Typed HIR."""

from __future__ import annotations

from collections.abc import Iterable

from .ast_nodes import SourceLocation, TypeRef
from .capability_effect_contract_v1 import CAPABILITY_TYPES
from .semantic import ImportedModule, SemanticError
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


def type_parameters_of(declaration) -> tuple[str, ...]:
    return tuple(getattr(declaration, "type_parameters", ()))


def declaration_type(declaration, type_ref: TypeRef | None) -> TypeNode:
    """Parse a declaration-owned type and bind its declared parameters."""

    return bind_type_variables(
        parse_type_ref(type_ref), frozenset(type_parameters_of(declaration))
    )


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
        return expected.name == actual.name
    if isinstance(expected, GenericType) and isinstance(actual, NamedType):
        return expected.name == actual.name
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
        parse_type_ref(type_ref), frozenset(type_parameters_of(function))
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


def infer_declaration_mapping(
    declaration,
    evidence: Iterable[tuple[TypeRef, TypeNode]],
    location: SourceLocation,
    validator: "TypeContractValidator",
    *,
    subject: str,
    allow_missing: bool = False,
) -> dict[str, TypeNode]:
    """Infer aggregate type parameters from struct fields or enum payloads."""

    parameters = type_parameters_of(declaration)
    pairs = tuple(evidence)
    if not parameters:
        for type_ref, actual in pairs:
            expected = declaration_type(declaration, type_ref)
            require_assignable(expected, actual, subject, location)
            validator.validate_type(expected, location, subject)
        return {}

    mapping: dict[str, TypeNode] = {}
    for type_ref, actual in pairs:
        pattern = declaration_type(declaration, type_ref)
        _infer_pattern(pattern, actual, mapping, subject, location)

    missing = [name for name in parameters if name not in mapping]
    if missing and not allow_missing:
        raise SemanticError(
            "KS1307",
            f"{subject}: şu tip parametreleri çıkarılamadı: {', '.join(missing)}. "
            "Alan/payload değerleri yeterli tip kanıtı sağlamalıdır.",
            location,
        )
    for name in missing:
        mapping[name] = UnknownType()

    for name, actual in mapping.items():
        if validator.is_sensitive(actual):
            raise SemanticError(
                "KS2402",
                f"{subject}: {name} capability taşıyan {render_type(actual)} "
                "olamaz. Capability generic argümanları kapalıdır.",
                location,
            )

    for type_ref, actual in pairs:
        expected = substitute_type(declaration_type(declaration, type_ref), mapping)
        require_assignable(expected, actual, subject, location)
        validator.validate_type(expected, location, subject)
    return mapping


def instantiated_declaration_type(
    declaration, mapping: dict[str, TypeNode]
) -> TypeNode:
    parameters = type_parameters_of(declaration)
    if not parameters:
        return NamedType(declaration.name)
    return GenericType(
        declaration.name,
        tuple(mapping.get(name, UnknownType()) for name in parameters),
    )


def instantiate_function(
    function,
    arguments: tuple[TypeNode, ...],
    location: SourceLocation,
    validator: "TypeContractValidator",
) -> TypeNode:
    """Infer a generic call and return its fully substituted result type."""

    mapping = infer_function_mapping(function, arguments, location)
    missing = [name for name in type_parameters_of(function) if name not in mapping]
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
            refs = tuple(field.type_ref for field in declaration.fields)
            self._validate_declaration_parameters(declaration, refs, "struct")
            for field in declaration.fields:
                self.validate_type(
                    declaration_type(declaration, field.type_ref),
                    field.location,
                    f"'{declaration.name}.{field.name}' alanı",
                )
        for declaration in self.program.enums:
            refs = tuple(
                variant.payload_type
                for variant in declaration.variants
                if variant.payload_type is not None
            )
            self._validate_declaration_parameters(declaration, refs, "enum")
            for variant in declaration.variants:
                if variant.payload_type is not None:
                    self.validate_type(
                        declaration_type(declaration, variant.payload_type),
                        variant.location,
                        f"'{declaration.name}.{variant.name}' payload'u",
                    )
        for function in self.program.declarations:
            self.validate_function(function)

    def _validate_declaration_parameters(
        self, declaration, refs: tuple[TypeRef, ...], kind: str
    ) -> None:
        parameters = type_parameters_of(declaration)
        self._validate_parameter_names(declaration.name, parameters, declaration.location)
        if not parameters:
            return
        used: set[str] = set()
        for type_ref in refs:
            used.update(unresolved_type_variables(declaration_type(declaration, type_ref)))
        unused = [name for name in parameters if name not in used]
        if unused:
            raise SemanticError(
                "KS1307",
                f"'{declaration.name}' {kind} bildiriminde kullanılmayan tip "
                f"parametresi: {', '.join(unused)}.",
                declaration.location,
            )

    def _validate_parameter_names(
        self, owner: str, parameters: tuple[str, ...], location: SourceLocation
    ) -> None:
        seen: set[str] = set()
        for name in parameters:
            if name in seen:
                raise SemanticError(
                    "KS1307",
                    f"'{owner}' içinde '{name}' tip parametresi birden fazla tanımlandı.",
                    location,
                )
            if name in RESERVED_TYPE_PARAMETERS:
                raise SemanticError(
                    "KS1307",
                    f"'{name}' yerleşik veya capability tipi olduğu için tip parametresi olamaz.",
                    location,
                )
            seen.add(name)

    def validate_function(self, function) -> None:
        parameters = type_parameters_of(function)
        self._validate_parameter_names(function.name, parameters, function.location)
        if function.name == "main" and parameters:
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

    def _generic_declaration(self, name: str):
        declaration = self.structs.get(name)
        if declaration is None:
            declaration = self.enums.get(name)
        return declaration

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
            declaration = self._generic_declaration(type_node.name)
            if declaration is not None and type_parameters_of(declaration):
                raise SemanticError(
                    "KS1307",
                    f"{subject}: generic {type_node.name} tipi "
                    f"{len(type_parameters_of(declaration))} tip argümanı ister.",
                    location,
                )
            return

        declaration = self._generic_declaration(type_node.name)
        expected = GENERIC_ARITY.get(type_node.name)
        if expected is None and declaration is not None:
            expected = len(type_parameters_of(declaration))
        if expected is None or (declaration is not None and expected == 0):
            raise SemanticError(
                "KS1301",
                f"{subject}: '{type_node.name}' generic tip değildir.",
                location,
            )
        if len(type_node.arguments) != expected:
            raise SemanticError(
                "KS1301",
                f"{subject}: {type_node.name} {expected} tip argümanı bekler, "
                f"{len(type_node.arguments)} verildi.",
                location,
            )
        if type_node.name == "Map":
            key = type_node.arguments[0]
            if not isinstance(key, (TypeVariable, UnknownType)) and key != STRING:
                raise SemanticError(
                    "KS1301",
                    f"{subject}: Map anahtar tipi String olmalıdır, "
                    f"{render_type(key)} bulundu.",
                    location,
                )
        for argument in type_node.arguments:
            self.validate_type(argument, location, subject)
        if any(self.is_sensitive(argument) for argument in type_node.arguments):
            raise SemanticError(
                "KS2402",
                f"{subject}: capability değeri {type_node.name} generic argümanında "
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
            if any(self.is_sensitive(argument, seen) for argument in type_node.arguments):
                return True
            declaration = self._generic_declaration(type_node.name)
            if declaration is None:
                return False
            key = render_type(type_node)
            if key in seen:
                return False
            mapping = dict(zip(type_parameters_of(declaration), type_node.arguments))
            nested_seen = seen | {key}
            if hasattr(declaration, "fields"):
                return any(
                    self.is_sensitive(
                        substitute_type(declaration_type(declaration, field.type_ref), mapping),
                        nested_seen,
                    )
                    for field in declaration.fields
                )
            return any(
                variant.payload_type is not None
                and self.is_sensitive(
                    substitute_type(
                        declaration_type(declaration, variant.payload_type), mapping
                    ),
                    nested_seen,
                )
                for variant in declaration.variants
            )
        if type_node.name in CAPABILITY_TYPES:
            return True
        if type_node.name in seen:
            return False
        nested_seen = seen | {type_node.name}
        declaration = self.structs.get(type_node.name)
        if declaration is not None:
            return any(
                self.is_sensitive(declaration_type(declaration, field.type_ref), nested_seen)
                for field in declaration.fields
            )
        enum = self.enums.get(type_node.name)
        if enum is not None:
            return any(
                variant.payload_type is not None
                and self.is_sensitive(
                    declaration_type(enum, variant.payload_type), nested_seen
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
            "Generic bir bildirimde tip parametresi güvenli ve tek anlamlı biçimde çıkarılamadı.",
            "Koschei gizli dinamik tipe düşmez. Çelişen, eksik veya kullanılmayan tip parametreleri backend ayrışması üretir.",
            "Tip parametresini giriş, struct alanı veya enum payload konumunda kullanın ve aynı parametre için tutarlı yapısal tip sağlayın.",
            "struct Box<T> { value: T }\nfn first<T>(items: List<T>) -> Option<T> { return items.get(0) }",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS1307",
        Diagnostic(
            "KS1307",
            "Generic type inference failed",
            "A generic declaration type parameter could not be inferred safely and unambiguously.",
            "Koschei does not fall back to hidden dynamic typing. Conflicting, missing, or unused parameters would diverge across backends.",
            "Use the parameter in an input, struct field, or enum payload position and provide structurally consistent evidence.",
            "struct Box<T> { value: T }\nfn first<T>(items: List<T>) -> Option<T> { return items.get(0) }",
        ),
    )


_register_diagnostics()