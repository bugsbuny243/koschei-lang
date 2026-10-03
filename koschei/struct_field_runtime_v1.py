"""AST-free runtime law for mutating an already-constructed ordinary Struct.

The canonical checker owns whether a field assignment is legal and mutable.  This
module only enforces the sealed runtime facts again: receiver shape, declaration
identity, field identity, generic type evidence, and capability confinement.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .ast_nodes import SourceLocation, StructDeclaration
from .interpreter import KoscheiRuntimeError, StructValue


class StructFieldRuntimeError(KoscheiRuntimeError):
    pass


def struct_field_set_v1(
    receiver: Any,
    field_name: str,
    value: Any,
    *,
    structs: Mapping[str, StructDeclaration],
    contains_capability: Callable[[Any], bool],
    matches_type: Callable[..., bool],
    runtime_type_name: Callable[[Any], str],
    location: SourceLocation,
) -> Any:
    """Mutate one checked Struct field and return the assignment value.

    No source AST is executed here.  Generic field types are checked against the
    concrete type arguments already carried by ``StructValue``.
    """

    if not isinstance(receiver, StructValue):
        raise StructFieldRuntimeError(
            "KS5002",
            "Sealed MIR Struct field assignment received a non-Struct receiver.",
            location,
        )

    declaration = structs.get(receiver.type_name)
    if declaration is None:
        raise StructFieldRuntimeError(
            "KS3101",
            f"MIR Struct declaration bulunamadı: '{receiver.type_name}'.",
            location,
        )

    field = next((item for item in declaration.fields if item.name == field_name), None)
    if field is None:
        raise StructFieldRuntimeError(
            "KS3101",
            f"'{receiver.type_name}' struct'ında '{field_name}' alanı yok.",
            location,
        )

    if field_name not in receiver.fields:
        raise StructFieldRuntimeError(
            "KS5002",
            f"Sealed MIR Struct value is missing declared field '{field_name}'.",
            location,
        )

    if contains_capability(value):
        raise StructFieldRuntimeError(
            "KS3401",
            "Capability taşıyan değerler ordinary Struct alanına atanamaz; runtime type-laundering girişimini reddetti.",
            location,
        )

    parameters = tuple(getattr(declaration, "type_parameters", ()))
    arguments = tuple(getattr(receiver, "type_arguments", ()))
    if len(arguments) != len(parameters):
        raise StructFieldRuntimeError(
            "KS5002",
            "Sealed MIR Struct runtime generic arity disagrees with checked declaration.",
            location,
        )

    type_bindings = dict(zip(parameters, arguments)) if parameters else None
    expected_names = field.type_ref.names
    if not matches_type(
        value,
        expected_names,
        type_parameters=frozenset(parameters),
        type_bindings=type_bindings,
    ):
        raise StructFieldRuntimeError(
            "KS3401",
            f"'{receiver.type_name}.{field_name}' alanı {' or '.join(expected_names)} beklerken {runtime_type_name(value)} aldı.",
            location,
        )

    receiver.fields[field_name] = value
    return value


__all__ = ["StructFieldRuntimeError", "struct_field_set_v1"]
