"""Koschei (.ks) lexical scanner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class TokenType(Enum):
    # Keywords
    PURE = auto()
    STATEFUL = auto()
    FN = auto()
    LET = auto()
    MUT = auto()
    OR = auto()
    RETURN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    BREAK = auto()
    CONTINUE = auto()
    STRUCT = auto()
    ENUM = auto()
    MATCH = auto()
    IMPORT = auto()
    TRUE = auto()
    FALSE = auto()

    # Names and values
    TYPE = auto()
    IDENTIFIER = auto()
    STRING = auto()
    STRING_INTERP = auto()
    NUMBER = auto()
    COMMENT = auto()

    # Single-character symbols
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    COMMA = auto()
    COLON = auto()
    DOT = auto()
    EQUAL = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    SEMICOLON = auto()
    BANG = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()

    # Multi-character symbols
    ARROW = auto()
    FAT_ARROW = auto()
    EQUAL_EQUAL = auto()
    BANG_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    AMP_AMP = auto()
    PIPE_PIPE = auto()

    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: Any
    line: int
    column: int

    def __repr__(self) -> str:
        return (
            f"Token({self.type.name:<13}, {self.value!r}, "
            f"line={self.line}, column={self.column})"
        )


class LexerError(SyntaxError):
    """Raised when Koschei source cannot be tokenized."""


class Lexer:
    KEYWORDS = {
        "pure": TokenType.PURE,
        "stateful": TokenType.STATEFUL,
        "fn": TokenType.FN,
        "let": TokenType.LET,
        "mut": TokenType.MUT,
        "or": TokenType.OR,
        "return": TokenType.RETURN,
        "if": TokenType.IF,
        "else": TokenType.ELSE,
        "while": TokenType.WHILE,
        "for": TokenType.FOR,
        "in": TokenType.IN,
        "break": TokenType.BREAK,
        "continue": TokenType.CONTINUE,
        "struct": TokenType.STRUCT,
        "enum": TokenType.ENUM,
        "match": TokenType.MATCH,
        "import": TokenType.IMPORT,
        "true": TokenType.TRUE,
        "false": TokenType.FALSE,
    }

    BUILTIN_TYPES = {
        "SystemCaps",
        "NetRoot",
        "DiskRoot",
        "EnvRoot",
        "ProcessRoot",
        "NetCaps",
        "DiskCaps",
        "DiskReadCaps",
        "EnvCaps",
        "ProcessCaps",
        "List",
        "Map",
        "String",
        "Int",
        "Float",
        "Bool",
        "Void",
        "Error",
        "Result",
        "Option",
    }

    SINGLE_CHAR_TOKENS = {
        "(": TokenType.LEFT_PAREN,
        ")": TokenType.RIGHT_PAREN,
        "{": TokenType.LEFT_BRACE,
        "}": TokenType.RIGHT_BRACE,
        ",": TokenType.COMMA,
        ":": TokenType.COLON,
        ".": TokenType.DOT,
        "+": TokenType.PLUS,
        "*": TokenType.STAR,
        "%": TokenType.PERCENT,
        ";": TokenType.SEMICOLON,
        "[": TokenType.LEFT_BRACKET,
        "]": TokenType.RIGHT_BRACKET,
    }

    ESCAPES = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        '"': '"',
        "\\": "\\",
        "{": "{",
        "}": "}",
    }

    def __init__(self, source: str, *, keep_comments: bool = False) -> None:
        self.source = source
        self.keep_comments = keep_comments
        self.start = 0
        self.current = 0
        self.line = 1
        self.column = 1
        self.start_line = 1
        self.start_column = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        while not self._is_at_end():
            self.start = self.current
            self.start_line = self.line
            self.start_column = self.column
            self._scan_token()
        self.tokens.append(Token(TokenType.EOF, None, self.line, self.column))
        return self.tokens

    def _scan_token(self) -> None:
        char = self._advance()
        if char in {" ", "\r", "\t", "\n"}:
            return

        if char == "/":
            if self._match("/"):
                while self._peek() not in {"\n", "\0"}:
                    self._advance()
                if self.keep_comments:
                    self._add_token(
                        TokenType.COMMENT, self.source[self.start:self.current]
                    )
                return
            self._add_token(TokenType.SLASH, "/")
            return

        if char == '"':
            self._string()
            return
        if char.isdigit():
            self._number()
            return
        if char.isalpha() or char == "_":
            self._identifier()
            return

        if char == "-":
            if self._match(">"):
                self._add_token(TokenType.ARROW, "->")
            else:
                self._add_token(TokenType.MINUS, "-")
            return
        if char == "=":
            if self._match(">"):
                self._add_token(TokenType.FAT_ARROW, "=>")
            elif self._match("="):
                self._add_token(TokenType.EQUAL_EQUAL, "==")
            else:
                self._add_token(TokenType.EQUAL, "=")
            return
        if char == "!":
            if self._match("="):
                self._add_token(TokenType.BANG_EQUAL, "!=")
            else:
                self._add_token(TokenType.BANG, "!")
            return
        if char == "&":
            if self._match("&"):
                self._add_token(TokenType.AMP_AMP, "&&")
                return
            self._error("Beklenmeyen '&'. Mantıksal ve için '&&' kullanın.")
        if char == "|":
            if self._match("|"):
                self._add_token(TokenType.PIPE_PIPE, "||")
                return
            self._error("Beklenmeyen '|'. Mantıksal veya için '||' kullanın.")
        if char == "<":
            if self._match("="):
                self._add_token(TokenType.LESS_EQUAL, "<=")
            else:
                self._add_token(TokenType.LESS, "<")
            return
        if char == ">":
            if self._match("="):
                self._add_token(TokenType.GREATER_EQUAL, ">=")
            else:
                self._add_token(TokenType.GREATER, ">")
            return

        token_type = self.SINGLE_CHAR_TOKENS.get(char)
        if token_type is not None:
            self._add_token(token_type, char)
            return
        self._error(f"Geçersiz karakter: {char!r}")

    def _identifier(self) -> None:
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[self.start:self.current]
        token_type = self.KEYWORDS.get(text)
        if token_type is None:
            token_type = (
                TokenType.TYPE
                if text in self.BUILTIN_TYPES or text[:1].isupper()
                else TokenType.IDENTIFIER
            )
        self._add_token(token_type, text)

    def _number(self) -> None:
        while self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek_next().isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit():
                self._advance()
        text = self.source[self.start:self.current]
        self._add_token(TokenType.NUMBER, float(text) if is_float else int(text))

    def _string(self) -> None:
        segments: list[tuple[str, str]] = []
        text_parts: list[str] = []

        def flush_text() -> None:
            if text_parts:
                segments.append(("text", "".join(text_parts)))
                text_parts.clear()

        while not self._is_at_end():
            char = self._advance()
            if char == '"':
                flush_text()
                if any(kind == "expr" for kind, _ in segments):
                    self._add_token(TokenType.STRING_INTERP, tuple(segments))
                else:
                    self._add_token(
                        TokenType.STRING, segments[0][1] if segments else ""
                    )
                return
            if char == "\\":
                if self._is_at_end():
                    self._error("Tamamlanmamış kaçış dizisi.")
                escaped = self._advance()
                if escaped not in self.ESCAPES:
                    self._error(f"Geçersiz kaçış dizisi: \\{escaped}")
                text_parts.append(self.ESCAPES[escaped])
                continue
            if char == "{":
                expr_source = self._interpolation_expression()
                if not expr_source:
                    self._error("Boş interpolasyon: '{}' geçersizdir.")
                flush_text()
                segments.append(("expr", expr_source))
                continue
            if char == "}":
                self._error("Metin içinde tek '}' geçersizdir; '\\}' kullanın.")
            text_parts.append(char)
        self._error("Kapatılmamış metin değeri.")

    def _interpolation_expression(self) -> str:
        depth = 1
        expression: list[str] = []
        in_string = False
        escaped = False
        while not self._is_at_end():
            char = self._advance()
            if in_string:
                expression.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                elif char == "\n":
                    self._error("İnterpolasyon içindeki metin satır sonuna taşamaz.")
                continue
            if char == '"':
                in_string = True
                expression.append(char)
                continue
            if char == "{":
                depth += 1
                expression.append(char)
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    return "".join(expression).strip()
                expression.append(char)
                continue
            if char == "\n":
                self._error("İnterpolasyon '}' ile aynı satırda kapatılmalıdır.")
            expression.append(char)
        self._error("İnterpolasyon '}' ile kapatılmalıdır.")
        raise AssertionError("unreachable")

    def _add_token(self, token_type: TokenType, value: Any) -> None:
        self.tokens.append(
            Token(token_type, value, self.start_line, self.start_column)
        )

    def _advance(self) -> str:
        char = self.source[self.current]
        self.current += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _match(self, expected: str) -> bool:
        if self._is_at_end() or self.source[self.current] != expected:
            return False
        self._advance()
        return True

    def _peek(self) -> str:
        return "\0" if self._is_at_end() else self.source[self.current]

    def _peek_next(self) -> str:
        if self.current + 1 >= len(self.source):
            return "\0"
        return self.source[self.current + 1]

    def _is_at_end(self) -> bool:
        return self.current >= len(self.source)

    def _error(self, message: str) -> None:
        raise LexerError(
            f"[satır {self.start_line}, sütun {self.start_column}] {message}"
        )


def tokenize(source: str, *, keep_comments: bool = False) -> list[Token]:
    return Lexer(source, keep_comments=keep_comments).tokenize()
