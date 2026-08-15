"""V5 parser facade adding generic and high-assurance declarations."""

from __future__ import annotations

from ._parser_v09 import Parser as _ParserV09
from ._parser_v09 import ParserError, _OR_RETURN_STOP
from .ast_nodes import (
    EnumVariant,
    Expression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Parameter,
    Program,
    StructField,
    TypeRef,
)
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

    def _match_contextual(self, value: str) -> bool:
        if self._check(TokenType.IDENTIFIER) and self._peek().value == value:
            self._advance()
            return True
        return False

    def _consume_contextual(self, value: str, message: str):
        if self._match_contextual(value):
            return self._previous()
        self._error(self._peek(), message)
        raise AssertionError("unreachable")

    def parse(self) -> Program:
        declarations = []
        structs = []
        enums = []
        imports = []

        while not self._is_at_end():
            if self._check(TokenType.IMPORT):
                imports.append(self._import_declaration())
            elif self._check(TokenType.STATEFUL) or self._check(TokenType.STRUCT):
                structs.append(self._struct_declaration())
            elif self._check(TokenType.ENUM):
                enums.append(self._enum_declaration())
            else:
                declarations.append(self._function_declaration())

        return Program(
            tuple(declarations), tuple(structs), tuple(imports), tuple(enums)
        )

    def _or_handler(self) -> Expression:
        expression = self._logical_or()

        while self._match(TokenType.OR):
            or_token = self._previous()

            if self._match(TokenType.RETURN):
                return_token = self._previous()
                error: Expression | None = None
                next_token = self._peek()
                if (
                    next_token.type not in _OR_RETURN_STOP
                    and next_token.line == return_token.line
                ):
                    error = self._logical_or()
                expression = OrReturnExpression(
                    expression, error, self._location(or_token)
                )
                continue

            if self._check(TokenType.LEFT_BRACE):
                handler = self._block()
                expression = OrBlockExpression(
                    expression, handler, self._location(or_token)
                )
                continue

            fallback = self._logical_or()
            expression = OrElseExpression(
                expression, fallback, self._location(or_token)
            )

        return expression

    def _struct_declaration(self) -> GenericStructDeclaration:
        is_stateful = self._match(TokenType.STATEFUL)
        stateful_token = self._previous() if is_stateful else None
        struct_token = self._consume(TokenType.STRUCT, "'struct' bekleniyordu.")
        name = self._consume(TokenType.TYPE, "Struct adı büyük harfle başlamalıdır.")
        type_parameters = self._type_parameters("Struct")

        initial_state: str | None = None
        if is_stateful:
            self._consume_contextual(
                "starts",
                "stateful struct tip parametresinden sonra 'starts State' bekleniyordu.",
            )
            marker = self._consume(
                TokenType.TYPE,
                "stateful struct başlangıç state'i büyük harfle başlayan bir tip olmalıdır.",
            )
            initial_state = marker.value

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
            name=name.value,
            fields=tuple(fields),
            location=self._location(stateful_token or struct_token),
            type_parameters=type_parameters,
            is_stateful=is_stateful,
            initial_state=initial_state,
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
        is_pure = self._match(TokenType.PURE)
        pure_token = self._previous() if is_pure else None
        is_transition = self._match_contextual("transition")
        transition_token = self._previous() if is_transition else None
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
            location=self._location(pure_token or transition_token or fn_token),
            is_pure=is_pure,
            type_parameters=type_parameters,
            is_transition=is_transition,
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
