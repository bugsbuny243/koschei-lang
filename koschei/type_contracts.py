"""Structural type-contract validation for the V5 Typed HIR migration."""

from __future__ import annotations

from .ast_nodes import SourceLocation
from .semantic import CAPABILITY_TYPES, ImportedModule, SemanticError
from .type_system import (
    STRING,
    GenericType,
    NamedType,
    TypeNode,
    UnionType,
    UnknownType,
    alternatives,
    parse_type_ref,
    render_type,
)

GENERIC_ARITY = {"Option": 1, "Result": 2, "List": 1, "Map": 2}
COLLECTION_NAMES = {"List", "Map"}
CONTAINER_NAMES = {"Option", "Result", "List", "Map"}


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
            for parameter in function.parameters:
                self.validate_type(
                    parse_type_ref(parameter.type_ref),
                    parameter.location,
                    f"'{function.name}.{parameter.name}' parametresi",
                )
            if function.return_type is not None:
                self.validate_type(
                    parse_type_ref(function.return_type),
                    function.return_type.location,
                    f"'{function.name}' dönüş tipi",
                )

    def validate_type(
        self, type_node: TypeNode, location: SourceLocation, subject: str
    ) -> None:
        if isinstance(type_node, UnknownType):
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
        if isinstance(type_node, UnknownType):
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
