"""Parser for the first native Koschei Universe declarations.

This is a narrow front-end slice over the real Koschei lexer. It exists so the
new native sigils have an actual parsed AST before they are integrated into the
larger legacy-compatible Program AST and Typed HIR pipeline.
"""
from __future__ import annotations

from .ast_nodes import SourceLocation
from .lexer import Token, TokenType, tokenize
from .native_sigil_ast_v1 import NativeSigilDeclaration, NativeSigilProgram


_SIGIL_TOKEN_TO_TEXT = {
    TokenType.KA: "ka",
    TokenType.VOR: "vor",
    TokenType.SHI: "shi",
    TokenType.THAL: "thal",
    TokenType.NUR: "nur",
}


class NativeSigilParserError(SyntaxError):
    pass


class NativeSigilParser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.current = 0

    @classmethod
    def from_source(cls, source: str) -> "NativeSigilParser":
        return cls(tokenize(source))

    def parse(self) -> NativeSigilProgram:
        declarations: list[NativeSigilDeclaration] = []
        while not self._check(TokenType.EOF):
            declarations.append(self._declaration())
        try:
            return NativeSigilProgram(tuple(declarations))
        except ValueError as error:
            raise NativeSigilParserError(str(error)) from error

    def _declaration(self) -> NativeSigilDeclaration:
        token = self._peek()
        sigil = _SIGIL_TOKEN_TO_TEXT.get(token.type)
        if sigil is None:
            self._error(token, "ka/vor/shi/thal/nur declaration expected")
        self._advance()

        subject = self._peek()
        if subject.type not in {TokenType.IDENTIFIER, TokenType.TYPE}:
            self._error(subject, f"{sigil} requires a subject name")
        self._advance()

        # v1 deliberately requires an explicit terminator. This prevents the
        # parser from guessing where one semantic root ends and the next begins.
        self._consume(TokenType.SEMICOLON, "native sigil declaration must end with ';'")

        return NativeSigilDeclaration(
            sigil=sigil,
            subject=str(subject.value),
            location=SourceLocation(token.line, token.column),
        )

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _advance(self) -> Token:
        token = self.tokens[self.current]
        if token.type is not TokenType.EOF:
            self.current += 1
        return token

    def _check(self, token_type: TokenType) -> bool:
        return self._peek().type is token_type

    def _consume(self, token_type: TokenType, message: str) -> Token:
        if self._check(token_type):
            return self._advance()
        self._error(self._peek(), message)
        raise AssertionError("unreachable")

    @staticmethod
    def _error(token: Token, message: str) -> None:
        raise NativeSigilParserError(
            f"[line {token.line}, column {token.column}] {message}"
        )


def parse_native_sigils(source: str) -> NativeSigilProgram:
    return NativeSigilParser.from_source(source).parse()
