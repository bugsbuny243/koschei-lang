"""V5 parser facade adding generic declarations to the v0.9 parser."""

from __future__ import annotations

from ._parser_v09 import Parser as _ParserV09
from ._parser_v09 import ParserError
from .ast_nodes import EnumVariant, Expression, Parameter, StructField, TypeRef
from .generic_nodes import (
    GenericEnumDeclaration,
    GenericFunctionDeclaration,
    GenericStructDeclaration,
)
from .lexer import TokenType, tokenize


class Parser(_ParserV09):
    @classmethod
    def from_source(cls, source: str) -> "Parser":
        return cls(tokenize(source))

    def _struct_declaration(self) -> GenericStructDeclaration:
        struct_token = self._consume(TokenType.STRUCT, "'struct' bekleniyordu.")
        name = self._consume(TokenType.TYPE, "Struct adı büyük harfle başlamalıdır.")
        type_parameters = self._type_parameters("Struct")
        self._consume(TokenType.LEFT_BRACE, "Struct adından sonra '{' bekleniyordu.")

        fields: list[StructField] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            field_name = self._consume(TokenType.IDENTIFIER, "Alan adı bekleniyordu.")
            self._consume(TokenType.COLON, "Alan adından sonra ':' bekleniyordu.")
            type_ref = self._type_ref()
            fields.append(
                StructField(field_name.value, type_ref, self._location(field_name))
            )
            if not self._match(TokenType.COMMA):
                break

        self._consume(TokenType.RIGHT_BRACE, "Struct sonunda '}' bekleniyordu.")
        return GenericStructDeclaration(
            name.value,
            tuple(fields),
            self._location(struct_token),
            type_parameters,
        )

    def _enum_declaration(self) -> GenericEnumDeclaration:
        enum_token = self._consume(TokenType.ENUM, "'enum' bekleniyordu.")
        name = self._consume(TokenType.TYPE, "Enum adı büyük harfle başlamalıdır.")
        type_parameters = self._type_parameters("Enum")
        self._consume(TokenType.LEFT_BRACE, "Enum adından sonra '{' bekleniyordu.")

        variants: list[EnumVariant] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            variant = self._consume(
                TokenType.TYPE, "Enum varyantı büyük harfle başlamalıdır."
            )
            payload_type: TypeRef | None = None
            if self._match(TokenType.LEFT_PAREN):
                payload_type = self._type_ref()
                self._consume(
                    TokenType.RIGHT_PAREN,
                    "Enum varyantı payload tipinden sonra ')' bekleniyordu.",
                )
            variants.append(
                EnumVariant(variant.value, payload_type, self._location(variant))
            )
            if not self._match(TokenType.COMMA):
                break
            if self._check(TokenType.RIGHT_BRACE):
                break

        self._consume(TokenType.RIGHT_BRACE, "Enum sonunda '}' bekleniyordu.")
        return GenericEnumDeclaration(
            name.value,
            tuple(variants),
            self._location(enum_token),
            type_parameters,
        )

    def _function_declaration(self) -> GenericFunctionDeclaration:
        fn_token = self._consume(TokenType.FN, "Fonksiyon 'fn' ile başlamalıdır.")
        name = self._consume(TokenType.IDENTIFIER, "Fonksiyon adı bekleniyordu.")
        type_parameters = self._type_parameters("Fonksiyon")
        self._consume(TokenType.LEFT_PAREN, "Fonksiyon adından sonra '(' bekleniyordu.")

        parameters: list[Parameter] = []
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                parameters.append(self._parameter())
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RIGHT_PAREN):
                    break

        self._consume(TokenType.RIGHT_PAREN, "Parametrelerden sonra ')' bekleniyordu.")

        return_type: TypeRef | None = None
        if self._match(TokenType.ARROW):
            return_type = self._type_ref()

        body = self._block()
        return GenericFunctionDeclaration(
            name=name.value,
            parameters=tuple(parameters),
            return_type=return_type,
            body=body,
            location=self._location(fn_token),
            type_parameters=type_parameters,
        )

    def _type_parameters(self, subject: str = "Bildirim") -> tuple[str, ...]:
        if not self._match(TokenType.LESS):
            return ()

        parameters: list[str] = []
        while True:
            parameter = self._consume(
                TokenType.TYPE,
                f"{subject} tip parametresi büyük harfle başlamalıdır.",
            )
            parameters.append(parameter.value)
            if not self._match(TokenType.COMMA):
                break
        self._consume(
            TokenType.GREATER,
            f"{subject} tip parametrelerinden sonra '>' bekleniyordu.",
        )
        return tuple(parameters)


def parse_expression(source: str) -> Expression:
    parser = Parser.from_source(source)
    expression = parser._expression()
    if not parser._is_at_end():
        parser._error(
            parser._peek(),
            "İnterpolasyon içinde tek bir ifade bekleniyordu.",
        )
    return expression


def parse(source: str):
    return Parser.from_source(source).parse()
