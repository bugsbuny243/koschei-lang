"""V5 parser facade adding generic function declarations to the v0.9 parser."""

from __future__ import annotations

from ._parser_v09 import Parser as _ParserV09
from ._parser_v09 import ParserError
from .ast_nodes import Expression, Parameter, TypeRef
from .generic_nodes import GenericFunctionDeclaration
from .lexer import TokenType, tokenize


class Parser(_ParserV09):
    @classmethod
    def from_source(cls, source: str) -> "Parser":
        return cls(tokenize(source))

    def _function_declaration(self) -> GenericFunctionDeclaration:
        fn_token = self._consume(TokenType.FN, "Fonksiyon 'fn' ile başlamalıdır.")
        name = self._consume(TokenType.IDENTIFIER, "Fonksiyon adı bekleniyordu.")
        type_parameters = self._type_parameters()
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

    def _type_parameters(self) -> tuple[str, ...]:
        if not self._match(TokenType.LESS):
            return ()

        parameters: list[str] = []
        while True:
            parameter = self._consume(
                TokenType.TYPE,
                "Generic fonksiyon tip parametresi büyük harfle başlamalıdır.",
            )
            parameters.append(parameter.value)
            if not self._match(TokenType.COMMA):
                break
        self._consume(
            TokenType.GREATER,
            "Generic fonksiyon tip parametrelerinden sonra '>' bekleniyordu.",
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
