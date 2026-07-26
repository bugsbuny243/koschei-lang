"""Koschei (.ks) için recursive-descent parser.

Öncelik zinciri (düşükten yükseğe):
    assignment -> or_handler -> logical_or (||) -> logical_and (&&)
    -> equality (== !=) -> comparison (< <= > >=)
    -> term (+ -) -> factor (* /) -> unary (! -) -> call -> primary

'or' üç biçimde ele alınır:
    ifade or return [hata]   -> OrReturnExpression
    ifade or { ... }         -> OrBlockExpression
    ifade or varsayilan      -> OrElseExpression
"""

from __future__ import annotations

from .ast_nodes import (
    AssignmentExpression,
    ImportDeclaration,
    ForStatement,
    ListLiteral,
    MapLiteral,
    StructDeclaration,
    StructField,
    StructLiteral,
    BinaryExpression,
    Block,
    CallExpression,
    Expression,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    InterpolatedString,
    LetStatement,
    Literal,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Parameter,
    Program,
    ReturnStatement,
    SourceLocation,
    Statement,
    TypeRef,
    UnaryExpression,
    WhileStatement,
)
from .lexer import Token, TokenType, tokenize


class ParserError(SyntaxError):
    """Koschei token akışı geçerli bir programa dönüştürülemediğinde yükseltilir."""


# 'or return' sonrasında hata ifadesi ARAMAYACAĞIMIZ tokenlar:
# blok sonu, noktalı virgül veya yeni bir statement başlangıcı.
_OR_RETURN_STOP = {
    TokenType.RIGHT_BRACE,
    TokenType.SEMICOLON,
    TokenType.LET,
    TokenType.RETURN,
    TokenType.IF,
    TokenType.WHILE,
    TokenType.FN,
    TokenType.EOF,
}


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.current = 0

    @classmethod
    def from_source(cls, source: str) -> "Parser":
        return cls(tokenize(source))

    def parse(self) -> Program:
        declarations: list[FunctionDeclaration] = []
        structs: list[StructDeclaration] = []
        imports: list[ImportDeclaration] = []

        while not self._is_at_end():
            if self._check(TokenType.IMPORT):
                imports.append(self._import_declaration())
            elif self._check(TokenType.STRUCT):
                structs.append(self._struct_declaration())
            else:
                declarations.append(self._function_declaration())

        return Program(tuple(declarations), tuple(structs), tuple(imports))

    def _import_declaration(self) -> ImportDeclaration:
        import_token = self._consume(TokenType.IMPORT, "'import' bekleniyordu.")
        name = self._consume(
            TokenType.IDENTIFIER, "Modül adı küçük harfle başlamalıdır."
        )
        return ImportDeclaration(name.value, self._location(import_token))

    def _struct_declaration(self) -> StructDeclaration:
        struct_token = self._consume(TokenType.STRUCT, "'struct' bekleniyordu.")
        name = self._consume(TokenType.TYPE, "Struct adı büyük harfle başlamalıdır.")
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
        return StructDeclaration(
            name.value, tuple(fields), self._location(struct_token)
        )

    def _function_declaration(self) -> FunctionDeclaration:
        fn_token = self._consume(TokenType.FN, "Fonksiyon 'fn' ile başlamalıdır.")
        name = self._consume(TokenType.IDENTIFIER, "Fonksiyon adı bekleniyordu.")
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
        return FunctionDeclaration(
            name=name.value,
            parameters=tuple(parameters),
            return_type=return_type,
            body=body,
            location=self._location(fn_token),
        )

    def _parameter(self) -> Parameter:
        name = self._consume(TokenType.IDENTIFIER, "Parametre adı bekleniyordu.")
        self._consume(TokenType.COLON, "Parametre adından sonra ':' bekleniyordu.")
        type_ref = self._type_ref()
        return Parameter(name.value, type_ref, self._location(name))

    def _type_ref(self) -> TypeRef:
        first = self._consume(TokenType.TYPE, "Tip adı bekleniyordu.")
        names = [first.value]

        while self._match(TokenType.OR):
            next_type = self._consume(TokenType.TYPE, "'or' sonrasında tip adı bekleniyordu.")
            names.append(next_type.value)

        return TypeRef(tuple(names), self._location(first))

    def _block(self) -> Block:
        self._consume(TokenType.LEFT_BRACE, "Blok başlangıcı için '{' bekleniyordu.")
        statements: list[Statement] = []

        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            statements.append(self._statement())

        self._consume(TokenType.RIGHT_BRACE, "Blok sonunda '}' bekleniyordu.")
        return Block(tuple(statements))

    def _statement(self) -> Statement:
        if self._match(TokenType.LET):
            return self._let_statement(self._previous())
        if self._match(TokenType.RETURN):
            return self._return_statement(self._previous())
        if self._match(TokenType.IF):
            return self._if_statement(self._previous())
        if self._match(TokenType.WHILE):
            return self._while_statement(self._previous())
        if self._match(TokenType.FOR):
            return self._for_statement(self._previous())

        expression = self._expression()
        self._match(TokenType.SEMICOLON)
        return ExpressionStatement(expression, expression.location)

    def _let_statement(self, let_token: Token) -> LetStatement:
        is_mutable = self._match(TokenType.MUT)
        name = self._consume(TokenType.IDENTIFIER, "Değişken adı bekleniyordu.")
        self._consume(TokenType.EQUAL, "Değişken tanımında '=' bekleniyordu.")
        value = self._expression()
        self._match(TokenType.SEMICOLON)
        return LetStatement(
            name=name.value,
            is_mutable=is_mutable,
            value=value,
            location=self._location(let_token),
        )

    def _return_statement(self, return_token: Token) -> ReturnStatement:
        value: Expression | None = None
        if self._peek().type not in _OR_RETURN_STOP:
            value = self._expression()
        self._match(TokenType.SEMICOLON)
        return ReturnStatement(value, self._location(return_token))

    def _if_statement(self, if_token: Token) -> IfStatement:
        condition = self._expression()
        then_block = self._block()

        else_branch: Block | IfStatement | None = None
        if self._match(TokenType.ELSE):
            if self._match(TokenType.IF):
                else_branch = self._if_statement(self._previous())
            else:
                else_branch = self._block()

        return IfStatement(condition, then_block, else_branch, self._location(if_token))

    def _for_statement(self, for_token: Token) -> ForStatement:
        variable = self._consume(TokenType.IDENTIFIER, "Döngü değişkeni bekleniyordu.")
        self._consume(TokenType.IN, "Döngü değişkeninden sonra 'in' bekleniyordu.")
        iterable = self._expression()
        body = self._block()
        return ForStatement(
            variable.value, iterable, body, self._location(for_token)
        )

    def _while_statement(self, while_token: Token) -> WhileStatement:
        condition = self._expression()
        body = self._block()
        return WhileStatement(condition, body, self._location(while_token))

    # ------------------------------------------------------------------
    # İfadeler
    # ------------------------------------------------------------------

    def _expression(self) -> Expression:
        return self._assignment()

    def _assignment(self) -> Expression:
        expression = self._or_handler()

        if self._match(TokenType.EQUAL):
            equals = self._previous()
            value = self._assignment()
            if not isinstance(expression, (Identifier, MemberExpression)):
                self._error(equals, "Geçersiz atama hedefi.")
            return AssignmentExpression(expression, value, self._location(equals))

        return expression

    def _or_handler(self) -> Expression:
        expression = self._logical_or()

        while self._match(TokenType.OR):
            or_token = self._previous()

            # ifade or return [hata]
            if self._match(TokenType.RETURN):
                error: Expression | None = None
                if self._peek().type not in _OR_RETURN_STOP:
                    error = self._logical_or()
                expression = OrReturnExpression(
                    expression, error, self._location(or_token)
                )
                continue

            # ifade or { ... }
            if self._check(TokenType.LEFT_BRACE):
                handler = self._block()
                expression = OrBlockExpression(
                    expression, handler, self._location(or_token)
                )
                continue

            # ifade or varsayilan
            fallback = self._logical_or()
            expression = OrElseExpression(
                expression, fallback, self._location(or_token)
            )

        return expression

    def _logical_or(self) -> Expression:
        expression = self._logical_and()
        while self._match(TokenType.PIPE_PIPE):
            operator = self._previous()
            right = self._logical_and()
            expression = BinaryExpression(
                expression, "||", right, self._location(operator)
            )
        return expression

    def _logical_and(self) -> Expression:
        expression = self._equality()
        while self._match(TokenType.AMP_AMP):
            operator = self._previous()
            right = self._equality()
            expression = BinaryExpression(
                expression, "&&", right, self._location(operator)
            )
        return expression

    def _equality(self) -> Expression:
        expression = self._comparison()
        while self._match(TokenType.EQUAL_EQUAL, TokenType.BANG_EQUAL):
            operator = self._previous()
            right = self._comparison()
            expression = BinaryExpression(
                expression, operator.value, right, self._location(operator)
            )
        return expression

    def _comparison(self) -> Expression:
        expression = self._term()
        while self._match(
            TokenType.LESS,
            TokenType.LESS_EQUAL,
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
        ):
            operator = self._previous()
            right = self._term()
            expression = BinaryExpression(
                expression, operator.value, right, self._location(operator)
            )
        return expression

    def _term(self) -> Expression:
        expression = self._factor()
        while self._match(TokenType.PLUS, TokenType.MINUS):
            operator = self._previous()
            right = self._factor()
            expression = BinaryExpression(
                expression, operator.value, right, self._location(operator)
            )
        return expression

    def _factor(self) -> Expression:
        expression = self._unary()
        while self._match(TokenType.STAR, TokenType.SLASH):
            operator = self._previous()
            right = self._unary()
            expression = BinaryExpression(
                expression, operator.value, right, self._location(operator)
            )
        return expression

    def _unary(self) -> Expression:
        if self._match(TokenType.BANG, TokenType.MINUS):
            operator = self._previous()
            operand = self._unary()
            return UnaryExpression(
                operator.value, operand, self._location(operator)
            )
        return self._call()

    def _call(self) -> Expression:
        expression = self._primary()

        while True:
            if self._match(TokenType.LEFT_PAREN):
                expression = self._finish_call(expression, self._previous())
            elif self._match(TokenType.DOT):
                member = self._consume(
                    TokenType.IDENTIFIER,
                    "'.' sonrasında alan veya metot adı bekleniyordu.",
                )
                expression = MemberExpression(
                    expression, member.value, self._location(member)
                )
            else:
                break

        return expression

    def _finish_call(self, callee: Expression, left_paren: Token) -> CallExpression:
        arguments: list[Expression] = []
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                arguments.append(self._expression())
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RIGHT_PAREN):
                    break

        self._consume(TokenType.RIGHT_PAREN, "Fonksiyon çağrısı sonunda ')' bekleniyordu.")
        return CallExpression(callee, tuple(arguments), self._location(left_paren))

    def _primary(self) -> Expression:
        if self._match(TokenType.STRING, TokenType.NUMBER):
            token = self._previous()
            return Literal(token.value, self._location(token))

        if self._match(TokenType.TRUE):
            return Literal(True, self._location(self._previous()))

        if self._match(TokenType.FALSE):
            return Literal(False, self._location(self._previous()))

        if self._match(TokenType.STRING_INTERP):
            token = self._previous()
            return self._interpolated_string(token)

        if self._match(TokenType.LEFT_BRACKET):
            return self._list_literal(self._previous())

        if self._match(TokenType.LEFT_BRACE):
            return self._map_literal(self._previous())

        if self._match(TokenType.IDENTIFIER, TokenType.TYPE):
            token = self._previous()
            # 'UserProfile { ... }' bir struct literalidir. Tip adları büyük
            # harfle başladığı için blok başlangıcıyla karışmaz.
            if token.type is TokenType.TYPE and self._check(TokenType.LEFT_BRACE):
                return self._struct_literal(token)
            return Identifier(token.value, self._location(token))

        if self._match(TokenType.LEFT_PAREN):
            expression = self._expression()
            self._consume(TokenType.RIGHT_PAREN, "İfade sonunda ')' bekleniyordu.")
            return expression

        self._error(self._peek(), "İfade bekleniyordu.")

    def _list_literal(self, bracket: Token) -> ListLiteral:
        items: list[Expression] = []
        if not self._check(TokenType.RIGHT_BRACKET):
            while True:
                items.append(self._expression())
                if not self._match(TokenType.COMMA):
                    break
                # Çok satırlı literallerde sondaki virgül serbesttir.
                if self._check(TokenType.RIGHT_BRACKET):
                    break
        self._consume(TokenType.RIGHT_BRACKET, "Liste sonunda ']' bekleniyordu.")
        return ListLiteral(tuple(items), self._location(bracket))

    def _map_literal(self, brace: Token) -> MapLiteral:
        entries: list[tuple[Expression, Expression]] = []
        if not self._check(TokenType.RIGHT_BRACE):
            while True:
                key = self._expression()
                self._consume(
                    TokenType.COLON,
                    "Map anahtarından sonra ':' bekleniyordu.",
                )
                value = self._expression()
                entries.append((key, value))
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RIGHT_BRACE):
                    break
        self._consume(TokenType.RIGHT_BRACE, "Map sonunda '}' bekleniyordu.")
        return MapLiteral(tuple(entries), self._location(brace))

    def _struct_literal(self, type_token: Token) -> StructLiteral:
        self._consume(TokenType.LEFT_BRACE, "Struct literalinde '{' bekleniyordu.")
        fields: list[tuple[str, Expression]] = []

        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            name = self._consume(TokenType.IDENTIFIER, "Alan adı bekleniyordu.")
            self._consume(TokenType.COLON, "Alan adından sonra ':' bekleniyordu.")
            fields.append((name.value, self._expression()))
            if not self._match(TokenType.COMMA):
                break

        self._consume(TokenType.RIGHT_BRACE, "Struct literalinde '}' bekleniyordu.")
        return StructLiteral(
            type_token.value, tuple(fields), self._location(type_token)
        )

    def _interpolated_string(self, token: Token) -> InterpolatedString:
        location = self._location(token)
        parts: list[Expression] = []

        for kind, content in token.value:
            if kind == "text":
                parts.append(Literal(content, location))
                continue

            # "user.email" -> Identifier / MemberExpression zinciri
            names = content.split(".")
            expression: Expression = Identifier(names[0], location)
            for member in names[1:]:
                expression = MemberExpression(expression, member, location)
            parts.append(expression)

        return InterpolatedString(tuple(parts), location)

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _match(self, *types: TokenType) -> bool:
        for token_type in types:
            if self._check(token_type):
                self._advance()
                return True
        return False

    def _consume(self, token_type: TokenType, message: str) -> Token:
        if self._check(token_type):
            return self._advance()
        self._error(self._peek(), message)

    def _check(self, token_type: TokenType) -> bool:
        if self._is_at_end():
            return token_type is TokenType.EOF
        return self._peek().type is token_type

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.current += 1
        return self._previous()

    def _is_at_end(self) -> bool:
        return self._peek().type is TokenType.EOF

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    @staticmethod
    def _location(token: Token) -> SourceLocation:
        return SourceLocation(token.line, token.column)

    @staticmethod
    def _error(token: Token, message: str) -> None:
        raise ParserError(f"[satır {token.line}, sütun {token.column}] {message}")


def parse(source: str) -> Program:
    """Kaynak metni tek çağrıda AST'ye dönüştürür."""
    return Parser.from_source(source).parse()
