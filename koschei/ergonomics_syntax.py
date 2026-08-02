"""Lexer, parser, formatter and syntax diagnostics for v0.10."""
from __future__ import annotations
from . import _formatter_v09 as fmt
from . import _parser_v09 as p09
from . import ast_nodes as ast
from . import diagnostics
from . import lexer
from .ergonomics_nodes import BreakStatement, ContinueStatement, LetStatement, MatchArm

_INSTALLED = False

def _lexer_error(self, message: str) -> None:
    raise lexer.LexerError(f"KS1001 [satır {self.start_line}, sütun {self.start_column}]: {message}")

def _parser_error(token, message: str) -> None:
    text = message.lower()
    code = "KS1005" if "match" in text or "varyant" in text else "KS1004" if "tip" in text else "KS1003" if any(x in text for x in ("adı", "isim", "bağlama", "değişken")) else "KS1002"
    raise p09.ParserError(f"{code} [satır {token.line}, sütun {token.column}]: {message}")

def _statement(self):
    if self._match(lexer.TokenType.BREAK):
        token = self._previous(); self._match(lexer.TokenType.SEMICOLON)
        return BreakStatement(self._location(token))
    if self._match(lexer.TokenType.CONTINUE):
        token = self._previous(); self._match(lexer.TokenType.SEMICOLON)
        return ContinueStatement(self._location(token))
    return _statement.original(self)

def _let_statement(self, token):
    mutable = self._match(lexer.TokenType.MUT)
    name = self._consume(lexer.TokenType.IDENTIFIER, "Değişken adı bekleniyordu.")
    annotation = self._type_ref() if self._match(lexer.TokenType.COLON) else None
    self._consume(lexer.TokenType.EQUAL, "Değişken tanımında tip anotasyonundan sonra '=' bekleniyordu.")
    value = self._expression(); self._match(lexer.TokenType.SEMICOLON)
    return LetStatement(name.value, mutable, value, self._location(token), annotation)

def _factor(self):
    expression = self._unary()
    while self._match(lexer.TokenType.STAR, lexer.TokenType.SLASH, lexer.TokenType.PERCENT):
        operator = self._previous()
        expression = ast.BinaryExpression(expression, operator.value, self._unary(), self._location(operator))
    return expression

def _match_expression(self, token):
    value = self._expression()
    self._consume(lexer.TokenType.LEFT_BRACE, "match değerinden sonra '{' bekleniyordu.")
    arms = []
    while not self._check(lexer.TokenType.RIGHT_BRACE) and not self._is_at_end():
        variant = self._consume(lexer.TokenType.TYPE, "match kolunda varyant adı bekleniyordu.")
        binding = None
        if self._match(lexer.TokenType.LEFT_PAREN):
            name = self._consume(lexer.TokenType.IDENTIFIER, "Varyant payload'ı için bağlama adı bekleniyordu.")
            binding = name.value
            self._consume(lexer.TokenType.RIGHT_PAREN, "match bağlamasından sonra ')' bekleniyordu.")
        self._consume(lexer.TokenType.FAT_ARROW, "match kolunda '=>' bekleniyordu.")
        body = self._block() if self._check(lexer.TokenType.LEFT_BRACE) else self._expression()
        arms.append(MatchArm(variant.value, binding, body, self._location(variant)))
        if self._match(lexer.TokenType.COMMA) or isinstance(body, ast.Block):
            continue
        break
    self._consume(lexer.TokenType.RIGHT_BRACE, "match sonunda '}' bekleniyordu.")
    return ast.MatchExpression(value, tuple(arms), self._location(token))

def _brace_is_literal(tokens, index):
    if index and tokens[index - 1].type is lexer.TokenType.FAT_ARROW:
        return False
    return _brace_is_literal.original(tokens, index)

def _register_diagnostics() -> None:
    rows = {
        "KS1001": ("Geçersiz sözcük veya karakter", "Kaynak kodda Koschei sözdiziminin tanımadığı bir karakter veya token var.", "Invalid token or character", "The source contains a character or token that is not valid Koschei syntax."),
        "KS1002": ("Beklenen sözdizimi öğesi eksik", "Parser beklenen ayraç veya ifadeyi bulamadı.", "Expected syntax element is missing", "The parser could not find an expected delimiter or expression."),
        "KS1003": ("Beklenen isim eksik", "Bu konumda bir değişken, fonksiyon, alan veya bağlama adı gerekli.", "Expected name is missing", "A variable, function, field, or binding name is required here."),
        "KS1004": ("Beklenen tip eksik", "Bu konumda geçerli bir Koschei tipi gerekli.", "Expected type is missing", "A valid Koschei type is required here."),
        "KS1005": ("Geçersiz match kolu", "match kolu varyant, payload bağlaması ve '=>' sözleşmesine uymuyor.", "Invalid match arm", "The match arm does not follow the variant, payload binding, and '=>' contract."),
        "KS1901": ("Döngü kontrolü döngü dışında", "break veya continue yalnızca for/while gövdesinde kullanılabilir.", "Loop control outside a loop", "break and continue may only be used inside a for or while body."),
        "KS3201": ("Geçersiz alan ataması", "Struct alanı yalnızca let mut ile bağlanmış doğrudan bir struct üzerinde değiştirilebilir.", "Invalid field assignment", "A struct field can only be changed through a directly bound struct declared with let mut."),
    }
    for code, (tt, ts, et, es) in rows.items():
        diagnostics.CATALOG.setdefault(code, diagnostics.Diagnostic(code, tt, ts, "Sözdizimi ve değişmezlik kuralları backend'ler arasında aynıdır.", "Bildirilen konumdaki sözdizimini veya let/let mut seçimini düzeltin.", "fn main() { let mut value: Int = 1 }"))
        diagnostics.ENGLISH_CATALOG.setdefault(code, diagnostics.Diagnostic(code, et, es, "Syntax and mutability rules are identical across backends.", "Correct the syntax at the reported location or choose let/let mut appropriately.", "fn main() { let mut value: Int = 1 }"))

def install_syntax_v010() -> None:
    global _INSTALLED
    if _INSTALLED: return
    p09._OR_RETURN_STOP.update({lexer.TokenType.BREAK, lexer.TokenType.CONTINUE})
    fmt.SPACED_OPERATORS.add(lexer.TokenType.PERCENT)
    fmt.STATEMENT_STARTERS.update({lexer.TokenType.BREAK, lexer.TokenType.CONTINUE})
    lexer.Lexer._error = _lexer_error
    p09.Parser._error = staticmethod(_parser_error)
    _statement.original = p09.Parser._statement; p09.Parser._statement = _statement
    p09.Parser._let_statement = _let_statement
    p09.Parser._factor = _factor
    p09.Parser._match_expression = _match_expression
    _brace_is_literal.original = fmt._brace_is_literal; fmt._brace_is_literal = _brace_is_literal
    _register_diagnostics(); _INSTALLED = True
