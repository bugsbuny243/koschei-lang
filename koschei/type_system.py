"""Structural type model used by the V5 typed-HIR migration.

The surface AST still carries the v0.9 ``TypeRef`` compatibility wrapper.  This
module converts that representation into immutable structural nodes so later
compiler passes no longer need to split generic and union types with ad-hoc
string operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .ast_nodes import TypeRef


@dataclass(frozen=True, slots=True)
class UnknownType:
    """A type that cannot yet be proven by the current migration slice."""


@dataclass(frozen=True, slots=True)
class NamedType:
    name: str


@dataclass(frozen=True, slots=True)
class GenericType:
    name: str
    arguments: tuple["TypeNode", ...]


@dataclass(frozen=True, slots=True)
class UnionType:
    options: tuple["TypeNode", ...]


TypeNode: TypeAlias = UnknownType | NamedType | GenericType | UnionType
UNKNOWN = UnknownType()
VOID = NamedType("Void")
BOOL = NamedType("Bool")
INT = NamedType("Int")
FLOAT = NamedType("Float")
STRING = NamedType("String")
ERROR = NamedType("Error")


def split_top_level(text: str, separator: str) -> tuple[str, ...]:
    """Split a type expression without cutting nested generic arguments."""

    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
            if depth < 0:
                raise ValueError(f"Unbalanced type expression: {text!r}")
        elif depth == 0 and text.startswith(separator, index):
            part = text[start:index].strip()
            if part:
                parts.append(part)
            index += len(separator)
            start = index
            continue
        index += 1
    if depth != 0:
        raise ValueError(f"Unbalanced type expression: {text!r}")
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


def parse_type_text(text: str) -> TypeNode:
    """Parse ``Result<List<Int>, Error> or Void`` into structural nodes."""

    text = text.strip()
    if not text or text == "_":
        return UNKNOWN

    union_parts = split_top_level(text, " or ")
    if len(union_parts) > 1:
        return union_type(*(parse_type_text(part) for part in union_parts))

    if "<" not in text:
        return NamedType(text)
    if not text.endswith(">"):
        raise ValueError(f"Invalid generic type expression: {text!r}")

    name, remainder = text.split("<", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"Generic type has no name: {text!r}")
    inner = remainder[:-1]
    arguments = tuple(parse_type_text(part) for part in split_top_level(inner, ","))
    if not arguments:
        raise ValueError(f"Generic type has no arguments: {text!r}")
    return GenericType(name, arguments)


def parse_type_ref(type_ref: TypeRef | None) -> TypeNode:
    if type_ref is None:
        return VOID
    return union_type(*(parse_type_text(name) for name in type_ref.names))


def render_type(type_node: TypeNode) -> str:
    if isinstance(type_node, UnknownType):
        return "_"
    if isinstance(type_node, NamedType):
        return type_node.name
    if isinstance(type_node, GenericType):
        arguments = ", ".join(render_type(item) for item in type_node.arguments)
        return f"{type_node.name}<{arguments}>"
    return " or ".join(render_type(item) for item in type_node.options)


def alternatives(type_node: TypeNode) -> tuple[TypeNode, ...]:
    if isinstance(type_node, UnionType):
        return type_node.options
    return (type_node,)


def union_type(*types: TypeNode) -> TypeNode:
    """Create a canonical, flattened union while preserving useful evidence."""

    flattened: list[TypeNode] = []
    for type_node in types:
        if isinstance(type_node, UnknownType):
            continue
        if isinstance(type_node, UnionType):
            flattened.extend(type_node.options)
        else:
            flattened.append(type_node)

    unique: dict[str, TypeNode] = {}
    for type_node in flattened:
        unique.setdefault(render_type(type_node), type_node)
    if not unique:
        return UNKNOWN
    ordered = tuple(unique[key] for key in sorted(unique))
    if len(ordered) == 1:
        return ordered[0]
    return UnionType(ordered)


def generic(name: str, *arguments: TypeNode) -> GenericType:
    return GenericType(name, tuple(arguments))


def is_named(type_node: TypeNode, name: str) -> bool:
    return isinstance(type_node, NamedType) and type_node.name == name


def success_type(type_node: TypeNode) -> TypeNode:
    """Return the value exposed after ``or`` / ``or return`` narrowing."""

    if isinstance(type_node, GenericType):
        if type_node.name == "Option" and len(type_node.arguments) == 1:
            return type_node.arguments[0]
        if type_node.name == "Result" and len(type_node.arguments) == 2:
            return type_node.arguments[0]
    if isinstance(type_node, UnionType):
        return union_type(
            *(item for item in type_node.options if not is_named(item, "Error"))
        )
    return type_node


def contains_named(type_node: TypeNode, names: set[str]) -> bool:
    if isinstance(type_node, NamedType):
        return type_node.name in names
    if isinstance(type_node, GenericType):
        return type_node.name in names or any(
            contains_named(argument, names) for argument in type_node.arguments
        )
    if isinstance(type_node, UnionType):
        return any(contains_named(option, names) for option in type_node.options)
    return False
