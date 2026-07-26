"""Koschei kanonik biçimlendiricisi (`ks fmt`).

Amaç: Koschei kodunun TEK bir doğru görünümü olsun. Biçim tartışması yoktur;
`ks fmt` ne diyorsa odur. Go'yu tanınabilir kılan `gofmt` ile aynı fikir:
biçim topluluk kararı değil, araç kararıdır.

Tasarım: **melez biçimlendirme.** Kanonik yapı token akışından kurulur —
süslü parantezler ve deyim anahtar kelimeleri (let/return/if/while/fn) her zaman
satır kırar, böylece tek satıra sıkıştırılmış kod açılır. Bunun dışında yazarın
satır yapısı korunur: tokenlardan deyim sınırı "tahmin etmek" yanlış
birleştirmelere yol açacağı için denenmez. Yorumlar korunur; girinti, aralık ve
boş satırlar normalize edilir.

Garantiler (testlerle sabitlenmiştir):
1. Değişmezlik (idempotency): format(format(x)) == format(x)
2. Anlam korunumu: biçimlendirme, yorum dışı token akışını DEĞİŞTİRMEZ
"""

from __future__ import annotations

from .lexer import Token, TokenType, tokenize

INDENT = "    "

# Kendinden önce boşluk istemeyen tokenlar
NO_SPACE_BEFORE = {
    TokenType.COMMA,
    TokenType.RIGHT_BRACKET,
    TokenType.COLON,
    TokenType.RIGHT_PAREN,
    TokenType.SEMICOLON,
    TokenType.DOT,
}

# Kendinden sonra boşluk istemeyen tokenlar
NO_SPACE_AFTER = {
    TokenType.LEFT_PAREN,
    TokenType.LEFT_BRACKET,
    TokenType.DOT,
    TokenType.BANG,
}

# İki yanında da tek boşluk isteyen işleçler
SPACED_OPERATORS = {
    TokenType.EQUAL,
    TokenType.EQUAL_EQUAL,
    TokenType.BANG_EQUAL,
    TokenType.LESS,
    TokenType.LESS_EQUAL,
    TokenType.GREATER,
    TokenType.GREATER_EQUAL,
    TokenType.PLUS,
    TokenType.MINUS,
    TokenType.STAR,
    TokenType.SLASH,
    TokenType.AMP_AMP,
    TokenType.PIPE_PIPE,
    TokenType.ARROW,
}

# Bir isim/değer başlangıcı sayılan tokenlar (tekil '-' ayrımı için)
VALUE_STARTS = {
    TokenType.IDENTIFIER,
    TokenType.RIGHT_BRACKET,
    TokenType.TYPE,
    TokenType.NUMBER,
    TokenType.STRING,
    TokenType.STRING_INTERP,
    TokenType.TRUE,
    TokenType.FALSE,
    TokenType.RIGHT_PAREN,
}

ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class FormatterError(Exception):
    """Kaynak biçimlendirilemediğinde yükseltilir."""


# Bir deyimin başlayabileceği anahtar kelimeler. Bunlardan önce satır kırılır —
# tek istisnalar: 'or return' (RETURN burada ifade içindedir) ve 'else if'.
STATEMENT_STARTERS = {
    TokenType.LET,
    TokenType.FOR,
    TokenType.STRUCT,
    TokenType.IMPORT,
    TokenType.RETURN,
    TokenType.IF,
    TokenType.WHILE,
    TokenType.FN,
}


def format_source(source: str) -> str:
    """Koschei kaynağını kanonik biçime getirir."""
    tokens = [
        token
        for token in tokenize(source, keep_comments=True)
        if token.type is not TokenType.EOF
    ]
    if not tokens:
        return ""

    rows = _logical_lines(tokens)
    return _render_rows(rows)


def _logical_lines(tokens: list[Token]) -> list[tuple[list[Token], bool]]:
    """Token akışını mantıksal satırlara böler.

    Kaynağın satır yapısı korunmaz; kanonik yapı tokenlardan yeniden kurulur.
    Yazarın bıraktığı boş satırlar (en fazla bir tane) korunur.
    """
    depths = _literal_depths(tokens)

    rows: list[tuple[list[Token], bool]] = []
    current: list[Token] = []
    current_blank = False
    previous_depth = 0

    for index, token in enumerate(tokens):
        if current:
            previous = current[-1]
            # Boş satır, kapanan satıra değil AÇILAN satıra aittir.
            gap = token.line > previous.line + 1
            if _breaks_before(token, previous, depths[index], previous_depth):
                rows.append((current, current_blank))
                current = []
                current_blank = gap
        current.append(token)
        previous_depth = depths[index]

    if current:
        rows.append((current, current_blank))
    return rows


def _literal_depths(tokens: list[Token]) -> list[int]:
    """Her token için struct/Map literali derinliğini hesaplar.

    Struct, Map ve bloklar aynı süslü parantezleri kullanır. Literal
    parantezleri blok gibi satır kırmamalıdır; bu yüzden açılış bağlamı ve
    Map'teki üst-seviye ':' işareti birlikte değerlendirilir.
    """
    depths: list[int] = []
    stack: list[bool] = []
    depth = 0

    for index, token in enumerate(tokens):
        if token.type is TokenType.LEFT_BRACE:
            is_literal = _brace_is_literal(tokens, index)
            stack.append(is_literal)
            depths.append(depth)
            if is_literal:
                depth += 1
        elif token.type is TokenType.RIGHT_BRACE:
            is_literal = stack.pop() if stack else False
            if is_literal:
                depth -= 1
                depths.append(depth + 1)
            else:
                depths.append(depth)
        else:
            depths.append(depth)

    return depths


def _brace_is_literal(tokens: list[Token], index: int) -> bool:
    if index == 0:
        return _brace_has_top_level_colon(tokens, index)

    previous = tokens[index - 1]
    if previous.type is TokenType.TYPE:
        # `struct User { ... }` bildirimdir; diğer `User { ... }` biçimleri
        # struct literalidir.
        return not (index >= 2 and tokens[index - 2].type is TokenType.STRUCT)

    if _brace_has_top_level_colon(tokens, index):
        return True

    # Boş Map (`{}`) için ':' sinyali yoktur; ifade başlangıcı bağlamını kullan.
    return previous.type in {
        TokenType.EQUAL,
        TokenType.COMMA,
        TokenType.LEFT_PAREN,
        TokenType.LEFT_BRACKET,
        TokenType.COLON,
        TokenType.RETURN,
    }


def _brace_has_top_level_colon(tokens: list[Token], index: int) -> bool:
    depth = 0
    for token in tokens[index + 1:]:
        if token.type in {
            TokenType.LEFT_BRACE,
            TokenType.LEFT_BRACKET,
            TokenType.LEFT_PAREN,
        }:
            depth += 1
        elif token.type in {
            TokenType.RIGHT_BRACE,
            TokenType.RIGHT_BRACKET,
            TokenType.RIGHT_PAREN,
        }:
            if token.type is TokenType.RIGHT_BRACE and depth == 0:
                return False
            depth = max(depth - 1, 0)
        elif token.type is TokenType.COLON and depth == 0:
            return True
    return False


def _breaks_before(
    token: Token, previous: Token, depth: int, previous_depth: int
) -> bool:
    # Yorum satır sonundaysa satırda kalır; kendi satırındaysa yeni satır açar.
    if token.type is TokenType.COMMENT:
        return token.line > previous.line
    if previous.type is TokenType.COMMENT:
        return True

    # Süslü parantez kuralları yalnızca BLOK parantezleri için geçerlidir;
    # struct literalinin içi satır kırmaz.
    # depth=0 olan bir RIGHT_BRACE blok kapatır. Hemen öncesinde Map/struct
    # literali kapanmış olsa bile blok kapanışı yeni satıra geçmelidir.
    if depth == 0 and token.type is TokenType.RIGHT_BRACE:
        return True

    if depth == 0 and previous_depth == 0:
        if previous.type is TokenType.LEFT_BRACE:
            return True
        if previous.type is TokenType.RIGHT_BRACE:
            return token.type is not TokenType.ELSE

    if depth == 0 and token.type in STATEMENT_STARTERS:
        # 'or return' tek bir ifadedir, bölünmez.
        if token.type is TokenType.RETURN and previous.type is TokenType.OR:
            return False
        # 'else if' tek satırda kalır.
        if token.type is TokenType.IF and previous.type is TokenType.ELSE:
            return False
        return True

    # Yazarın koyduğu satır sonu korunur. Anahtar kelimeyle başlamayan deyimler
    # (ör. arka arkaya iki 'println(...)' çağrısı) yalnızca bu kuralla ayrılır;
    # tokenlardan deyim sınırı çıkarmaya çalışmak yanlış birleştirmelere yol açar.
    return token.line > previous.line


def _render_rows(rows: list[tuple[list[Token], bool]]) -> str:
    output: list[str] = []
    depth = 0

    for index, (row, blank_before) in enumerate(rows):
        closes = _closes_first(row)
        if closes:
            depth = max(depth - 1, 0)

        allow_blank = (
            blank_before
            and index > 0
            and not closes
            and bool(output)
            and not output[-1].endswith("{")
        )
        if allow_blank:
            output.append("")

        output.append(INDENT * depth + _render_line(row))
        depth = max(depth + _net_braces(row, skip_leading_close=closes), 0)

    while output and not output[-1].strip():
        output.pop()

    return "\n".join(output) + "\n"


def check_source(source: str) -> bool:
    """Kaynak zaten kanonik biçimde mi?"""
    return format_source(source) == source


def _closes_first(row: list[Token]) -> bool:
    return bool(row) and row[0].type in {
        TokenType.RIGHT_BRACE,
        TokenType.RIGHT_BRACKET,
    }


def _net_braces(row: list[Token], *, skip_leading_close: bool) -> int:
    total = 0
    for index, token in enumerate(row):
        if token.type in {TokenType.LEFT_BRACE, TokenType.LEFT_BRACKET}:
            total += 1
        elif token.type in {TokenType.RIGHT_BRACE, TokenType.RIGHT_BRACKET}:
            if index == 0 and skip_leading_close:
                continue
            total -= 1
    return total


def _render_line(row: list[Token]) -> str:
    pieces: list[str] = []
    for index, token in enumerate(row):
        text = _render_token(token)
        if index == 0:
            pieces.append(text)
            continue

        previous = row[index - 1]
        if _needs_space(previous, token, row, index):
            pieces.append(" ")
        pieces.append(text)

    return "".join(pieces).rstrip()


def _needs_space(
    previous: Token, token: Token, row: list[Token], index: int
) -> bool:
    if (
        previous.type is TokenType.LEFT_BRACE
        and token.type is TokenType.RIGHT_BRACE
    ):
        return False
    if token.type in NO_SPACE_BEFORE:
        return False
    if previous.type in NO_SPACE_AFTER:
        return False

    # Çağrı parantezi: isimden hemen sonra boşluk yok -> f(x)
    if token.type is TokenType.LEFT_PAREN and previous.type in VALUE_STARTS:
        return False

    if previous.type is TokenType.COLON:
        return True

    if token.type in SPACED_OPERATORS or previous.type in SPACED_OPERATORS:
        # Tekil eksi: değer başlangıcı değilse birleşik yazılır -> -1, !flag
        if token.type is TokenType.MINUS and not _is_binary_position(row, index):
            return True
        if previous.type is TokenType.MINUS and not _is_binary_position(
            row, index - 1
        ):
            return False
        return True

    return True


def _is_binary_position(row: list[Token], index: int) -> bool:
    """Bu konumdaki '-' ikili işleç mi (yoksa tekil mi)?"""
    if index == 0:
        return False
    return row[index - 1].type in VALUE_STARTS


def _render_token(token: Token) -> str:
    if token.type is TokenType.STRING:
        return '"' + _escape(token.value) + '"'
    if token.type is TokenType.STRING_INTERP:
        return '"' + _render_interpolation(token.value) + '"'
    if token.type is TokenType.NUMBER:
        return repr(token.value) if isinstance(token.value, float) else str(token.value)
    if token.type is TokenType.COMMENT:
        return _normalize_comment(token.value)
    return str(token.value)


def _render_interpolation(segments: tuple[tuple[str, str], ...]) -> str:
    parts: list[str] = []
    for kind, content in segments:
        if kind == "text":
            parts.append(_escape(content))
        else:
            parts.append("{" + content + "}")
    return "".join(parts)


def _escape(value: str) -> str:
    result: list[str] = []
    for character in value:
        if character in ESCAPES:
            result.append(ESCAPES[character])
        elif character in "{}":
            result.append("\\" + character)
        else:
            result.append(character)
    return "".join(result)


def _normalize_comment(text: str) -> str:
    body = text[2:].strip()
    return f"// {body}" if body else "//"
