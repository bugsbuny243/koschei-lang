"""V5 formatter facade for generic and high-assurance declarations."""

from __future__ import annotations

from . import _formatter_v09 as _v09
from .lexer import Token, TokenType


def _is_generic_angle(row: list[Token], index: int) -> bool:
    token = row[index]
    if token.type is TokenType.LESS:
        if index == 0:
            return False
        if row[index - 1].type is TokenType.TYPE:
            return True
        return (
            row[index - 1].type is TokenType.IDENTIFIER
            and index >= 2
            and row[index - 2].type is TokenType.FN
        )
    if token.type is not TokenType.GREATER:
        return False
    depth = 0
    for cursor in range(index - 1, -1, -1):
        current = row[cursor]
        if current.type is TokenType.GREATER:
            depth += 1
        elif current.type is TokenType.LESS:
            if depth == 0:
                if cursor == 0:
                    return False
                if row[cursor - 1].type is TokenType.TYPE:
                    return True
                return (
                    row[cursor - 1].type is TokenType.IDENTIFIER
                    and cursor >= 2
                    and row[cursor - 2].type is TokenType.FN
                )
            depth -= 1
    return False


def _brace_is_literal(tokens: list[Token], index: int) -> bool:
    if index == 0:
        return _v09._brace_has_top_level_colon(tokens, index)

    header_start = index
    for cursor in range(index - 1, -1, -1):
        current = tokens[cursor]
        if current.type in {TokenType.LEFT_BRACE, TokenType.RIGHT_BRACE}:
            break
        if current.type in {TokenType.FN, TokenType.STRUCT, TokenType.ENUM}:
            header_start = cursor
            break
    if header_start < index and header_start + 2 < index:
        keyword = tokens[header_start].type
        name = tokens[header_start + 1].type
        generic = tokens[header_start + 2].type is TokenType.LESS
        if keyword is TokenType.FN and name is TokenType.IDENTIFIER and generic:
            return False
        if keyword in {TokenType.STRUCT, TokenType.ENUM} and name is TokenType.TYPE and generic:
            return False
    return _ORIGINAL_BRACE_IS_LITERAL(tokens, index)


def _needs_space(previous: Token, token: Token, row: list[Token], index: int) -> bool:
    if (
        previous.type is TokenType.GREATER
        and _is_generic_angle(row, index - 1)
        and token.type is TokenType.LEFT_PAREN
    ):
        return False
    return _ORIGINAL_NEEDS_SPACE(previous, token, row, index)


def _breaks_before(
    token: Token, previous: Token, depth: int, previous_depth: int
) -> bool:
    # High-assurance declaration prefixes stay attached to the declaration they
    # qualify. `transition`/`starts` are contextual identifiers, not globally
    # reserved keywords.
    if token.type is TokenType.FN and (
        previous.type is TokenType.PURE
        or (previous.type is TokenType.IDENTIFIER and previous.value == "transition")
    ):
        return False
    if token.type is TokenType.STRUCT and previous.type is TokenType.STATEFUL:
        return False
    return _ORIGINAL_BREAKS_BEFORE(token, previous, depth, previous_depth)


_ORIGINAL_BRACE_IS_LITERAL = _v09._brace_is_literal
_ORIGINAL_NEEDS_SPACE = _v09._needs_space
_ORIGINAL_BREAKS_BEFORE = _v09._breaks_before
_v09.STATEMENT_STARTERS.update({TokenType.PURE, TokenType.STATEFUL})
_v09._is_generic_angle = _is_generic_angle
_v09._brace_is_literal = _brace_is_literal
_v09._needs_space = _needs_space
_v09._breaks_before = _breaks_before

format_source = _v09.format_source
check_source = _v09.check_source
