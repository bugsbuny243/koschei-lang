"""Koschei parser tarafından üretilen AST düğümleri."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class SourceLocation:
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class TypeRef:
    names: tuple[str, ...]
    location: SourceLocation

    def __str__(self) -> str:
        return " or ".join(self.names)


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    type_ref: TypeRef
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ImportDeclaration:
    """import risk — aynı dizindeki risk.ks dosyasını modül olarak bağlar."""

    name: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class StructField:
    name: str
    type_ref: TypeRef
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class StructDeclaration:
    name: str
    fields: tuple[StructField, ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Identifier:
    name: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Literal:
    value: object
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class InterpolatedString:
    """"Selam {items.length()}" — metin ve normal ifade parçaları."""

    parts: tuple["Expression", ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class StructLiteral:
    """UserProfile { id: 1, username: "onur" }"""

    type_name: str
    fields: tuple[tuple[str, "Expression"], ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ListLiteral:
    """[1, 2, 3]"""

    items: tuple["Expression", ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MapLiteral:
    """{"musteri": "Ali", "aktif": true}"""

    entries: tuple[tuple["Expression", "Expression"], ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MemberExpression:
    object: "Expression"
    member: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class CallExpression:
    callee: "Expression"
    arguments: tuple["Expression", ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class AssignmentExpression:
    target: "Expression"
    value: "Expression"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class BinaryExpression:
    left: "Expression"
    operator: str
    right: "Expression"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class UnaryExpression:
    operator: str
    operand: "Expression"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class OrReturnExpression:
    """deger = ifade or return [hata]"""

    value: "Expression"
    error: "Expression | None"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class OrElseExpression:
    """deger = ifade or varsayilan"""

    value: "Expression"
    fallback: "Expression"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class OrBlockExpression:
    """deger = ifade or { ... }"""

    value: "Expression"
    handler: "Block"
    location: SourceLocation


Expression: TypeAlias = (
    Identifier
    | Literal
    | InterpolatedString
    | StructLiteral
    | ListLiteral
    | MapLiteral
    | MemberExpression
    | CallExpression
    | AssignmentExpression
    | BinaryExpression
    | UnaryExpression
    | OrReturnExpression
    | OrElseExpression
    | OrBlockExpression
)


@dataclass(frozen=True, slots=True)
class LetStatement:
    name: str
    is_mutable: bool
    value: Expression
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ReturnStatement:
    value: Expression | None
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ExpressionStatement:
    expression: Expression
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class IfStatement:
    condition: Expression
    then_block: "Block"
    else_branch: "Block | IfStatement | None"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class WhileStatement:
    condition: Expression
    body: "Block"
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ForStatement:
    """for item in items { ... }"""

    variable: str
    iterable: Expression
    body: "Block"
    location: SourceLocation


Statement: TypeAlias = (
    LetStatement
    | ReturnStatement
    | ExpressionStatement
    | IfStatement
    | WhileStatement
    | ForStatement
)


@dataclass(frozen=True, slots=True)
class Block:
    statements: tuple[Statement, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FunctionDeclaration:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: TypeRef | None
    body: Block
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Program:
    declarations: tuple[FunctionDeclaration, ...]
    structs: tuple[StructDeclaration, ...] = ()
    imports: tuple[ImportDeclaration, ...] = ()
