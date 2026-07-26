"""Erase V5 collection parameters for the v0.9 semantic compatibility pass."""

from __future__ import annotations

from .ast_nodes import (
    EnumDeclaration,
    EnumVariant,
    FunctionDeclaration,
    Parameter,
    Program,
    StructDeclaration,
    StructField,
    TypeRef,
)
from .semantic import ImportedModule
from .type_system import (
    GenericType,
    TypeNode,
    TypeVariable,
    UnionType,
    UNKNOWN,
    bind_type_variables,
    parse_type_text,
    render_type,
)


def erase_node(type_node: TypeNode) -> TypeNode:
    if isinstance(type_node, TypeVariable):
        return UNKNOWN
    if isinstance(type_node, GenericType):
        if type_node.name in {"List", "Map"}:
            from .type_system import NamedType

            return NamedType(type_node.name)
        return GenericType(
            type_node.name, tuple(erase_node(item) for item in type_node.arguments)
        )
    if isinstance(type_node, UnionType):
        return UnionType(tuple(erase_node(item) for item in type_node.options))
    return type_node


def erase_type_ref(
    type_ref: TypeRef | None, type_parameters: tuple[str, ...] = ()
) -> TypeRef | None:
    if type_ref is None:
        return None
    names = frozenset(type_parameters)
    return TypeRef(
        tuple(
            render_type(
                erase_node(bind_type_variables(parse_type_text(name), names))
            )
            for name in type_ref.names
        ),
        type_ref.location,
    )


def erase_function(function: FunctionDeclaration) -> FunctionDeclaration:
    return FunctionDeclaration(
        function.name,
        tuple(
            Parameter(
                parameter.name,
                erase_type_ref(parameter.type_ref, getattr(function, "type_parameters", ())),
                parameter.location,
            )
            for parameter in function.parameters
        ),
        erase_type_ref(function.return_type, getattr(function, "type_parameters", ())),
        function.body,
        function.location,
    )


def erase_struct(declaration: StructDeclaration) -> StructDeclaration:
    return StructDeclaration(
        declaration.name,
        tuple(
            StructField(field.name, erase_type_ref(field.type_ref), field.location)
            for field in declaration.fields
        ),
        declaration.location,
    )


def erase_enum(declaration: EnumDeclaration) -> EnumDeclaration:
    return EnumDeclaration(
        declaration.name,
        tuple(
            EnumVariant(
                variant.name,
                erase_type_ref(variant.payload_type),
                variant.location,
            )
            for variant in declaration.variants
        ),
        declaration.location,
    )


def erase_program(program: Program) -> Program:
    return Program(
        tuple(erase_function(item) for item in program.declarations),
        tuple(erase_struct(item) for item in program.structs),
        program.imports,
        tuple(erase_enum(item) for item in program.enums),
    )


def erase_imports(
    imports: dict[str, ImportedModule],
) -> dict[str, ImportedModule]:
    return {
        name: ImportedModule(
            module.name,
            {key: erase_function(function) for key, function in module.functions.items()},
            {key: erase_struct(declaration) for key, declaration in module.structs.items()},
            {key: erase_enum(declaration) for key, declaration in module.enums.items()},
        )
        for name, module in imports.items()
    }
