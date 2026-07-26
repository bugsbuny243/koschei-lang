"""Typed collection operations and union-safety rules."""

from __future__ import annotations

from .ast_nodes import SourceLocation
from .semantic import CAPABILITY_TYPES, SemanticError
from .type_system import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UNKNOWN,
    GenericType,
    NamedType,
    TypeNode,
    UnionType,
    UnknownType,
    alternatives,
    generic,
    is_named,
    render_type,
    union_type,
)


def method_type(
    receiver: TypeNode,
    method: str,
    arguments: tuple[TypeNode, ...],
    location: SourceLocation,
) -> TypeNode:
    del arguments
    if isinstance(receiver, UnionType):
        return union_type(
            *(method_type(item, method, (), location) for item in receiver.options)
        )
    if isinstance(receiver, UnknownType):
        return UNKNOWN
    if isinstance(receiver, NamedType) and receiver.name in CAPABILITY_TYPES:
        return UNKNOWN

    if is_named(receiver, "String"):
        result = {
            "length": INT,
            "to_int": generic("Option", INT),
            "to_float": generic("Option", FLOAT),
            "contains": BOOL,
            "trim": STRING,
            "split": generic("List", STRING),
            "join": STRING,
        }.get(method)
        if result is not None:
            return result

    if isinstance(receiver, GenericType) and receiver.name == "List":
        item = receiver.arguments[0] if receiver.arguments else UNKNOWN
        result = {
            "length": INT,
            "get": generic("Option", item),
            "push": receiver,
            "contains": BOOL,
            "sort": receiver,
            "filter": receiver,
        }.get(method)
        if result is not None:
            return result
    if is_named(receiver, "List"):
        return method_type(generic("List", UNKNOWN), method, (), location)

    if isinstance(receiver, GenericType) and receiver.name == "Map":
        key = receiver.arguments[0] if receiver.arguments else STRING
        value = receiver.arguments[1] if len(receiver.arguments) > 1 else UNKNOWN
        result = {
            "get": generic("Option", value),
            "set": receiver,
            "keys": generic("List", key),
            "contains": BOOL,
        }.get(method)
        if result is not None:
            return result
    if is_named(receiver, "Map"):
        return method_type(generic("Map", STRING, UNKNOWN), method, (), location)

    raise SemanticError(
        "KS1306",
        f"'{method}' işlemi {render_type(receiver)} tipi için güvenli değildir.",
        location,
    )


def binary_type(
    left: TypeNode,
    operator: str,
    right: TypeNode,
    location: SourceLocation,
) -> TypeNode:
    if operator in {"==", "!=", "<", "<=", ">", ">="}:
        _validate_pairs(left, right, operator, location, comparison=True)
        return BOOL
    if operator in {"&&", "||"}:
        _validate_pairs(left, right, operator, location, logical=True)
        return BOOL
    if operator in {"+", "-", "*", "/"}:
        _validate_pairs(left, right, operator, location)
        return union_type(left, right)
    return UNKNOWN


def _validate_pairs(
    left: TypeNode,
    right: TypeNode,
    operator: str,
    location: SourceLocation,
    *,
    comparison: bool = False,
    logical: bool = False,
) -> None:
    for left_item in alternatives(left):
        for right_item in alternatives(right):
            if isinstance(left_item, UnknownType) or isinstance(right_item, UnknownType):
                continue
            valid = left_item == right_item
            if logical:
                valid = is_named(left_item, "Bool") and is_named(right_item, "Bool")
            elif not comparison:
                left_name = left_item.name if isinstance(left_item, NamedType) else ""
                right_name = right_item.name if isinstance(right_item, NamedType) else ""
                valid = left_name == right_name and (
                    left_name in {"Int", "Float"}
                    or (left_name == "String" and operator == "+")
                )
            if not valid:
                raise SemanticError(
                    "KS1306",
                    f"'{operator}' işlemi koleksiyondan gelen olası "
                    f"{render_type(left_item)} ve {render_type(right_item)} tipleri "
                    "için güvenli değil.",
                    location,
                )


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    CATALOG.setdefault(
        "KS1306",
        Diagnostic(
            "KS1306",
            "Tipli koleksiyon işlemi güvenli değil",
            "List/Map içinden gelen bir değer üzerindeki işlem bütün olası tipler için geçerli değil.",
            "Typed HIR öğe tipini for, get ve or boyunca korur; bir union üyesinde geçersiz işlemi kabul etmek runtime sürprizi ve backend ayrışması üretirdi.",
            "Koleksiyonu tek öğe tipinde tutun, enum/match ile ayırın veya her olası tip için geçerli bir işlem kullanın.",
            'let names = ["Ada", "Lin"]\nfor name in names { println(name.trim()) }',
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS1306",
        Diagnostic(
            "KS1306",
            "Typed collection operation is unsafe",
            "An operation on a List/Map value is not valid for every possible element type.",
            "Typed HIR preserves element evidence through for, get and or narrowing; accepting an invalid union member would create runtime and backend divergence.",
            "Keep the collection homogeneous, use enum/match, or choose an operation valid for every possible type.",
            'let names = ["Ada", "Lin"]\nfor name in names { println(name.trim()) }',
        ),
    )


_register_diagnostics()
