"""Bounded, deterministic JSON core for Koschei data/v1.

This module deliberately does not expose Python's ``json`` value semantics.
JSON numbers remain exact decimal values and every attacker-controlled resource
is checked before the value can be advertised as a supported stdlib operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TypeAlias

SCHEMA: Final = "koschei.data-json/v1"


@dataclass(frozen=True, slots=True)
class Limits:
    max_input_bytes: int = 1_048_576
    max_output_bytes: int = 1_048_576
    max_nodes: int = 100_000
    max_depth: int = 64

    def validate(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_output_bytes", self.max_output_bytes),
            ("max_nodes", self.max_nodes),
            ("max_depth", self.max_depth),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")


DEFAULT_LIMITS: Final = Limits()


@dataclass(frozen=True, slots=True)
class Number:
    """An exact canonical JSON number.

    The text is normalized without converting through binary floating point.
    Equal decimal values therefore encode identically across bootstraps.
    """

    text: str

    def __post_init__(self) -> None:
        canonical = canonical_number(self.text)
        if canonical != self.text:
            raise ValueError(
                f"Number text must already be canonical: {self.text!r} -> {canonical!r}"
            )


JsonScalar: TypeAlias = None | bool | str | Number
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class DataError(Exception):
    code: str
    message: str
    offset: int

    def __str__(self) -> str:
        return f"{self.code} [byte {self.offset}]: {self.message}"


_HEX = frozenset("0123456789abcdefABCDEF")


def _is_ascii_digit(char: str) -> bool:
    return "0" <= char <= "9"


def canonical_number(text: str) -> str:
    """Return the data/v1 canonical representation of one valid JSON number."""
    if not isinstance(text, str) or not text:
        raise ValueError("JSON number must be a non-empty string")

    index = 0
    negative = False
    if text[index] == "-":
        negative = True
        index += 1
        if index == len(text):
            raise ValueError("missing digits after '-' in JSON number")

    int_start = index
    if text[index] == "0":
        index += 1
        if index < len(text) and _is_ascii_digit(text[index]):
            raise ValueError("leading zero in JSON number")
    elif "1" <= text[index] <= "9":
        index += 1
        while index < len(text) and _is_ascii_digit(text[index]):
            index += 1
    else:
        raise ValueError("invalid integer part in JSON number")
    integer = text[int_start:index]

    fraction = ""
    if index < len(text) and text[index] == ".":
        index += 1
        frac_start = index
        while index < len(text) and _is_ascii_digit(text[index]):
            index += 1
        if index == frac_start:
            raise ValueError("fraction requires at least one digit")
        fraction = text[frac_start:index]

    exponent = 0
    if index < len(text) and text[index] in "eE":
        index += 1
        exp_negative = False
        if index < len(text) and text[index] in "+-":
            exp_negative = text[index] == "-"
            index += 1
        exp_start = index
        while index < len(text) and _is_ascii_digit(text[index]):
            index += 1
        if index == exp_start:
            raise ValueError("exponent requires at least one digit")
        exp_digits = text[exp_start:index].lstrip("0") or "0"
        if len(exp_digits) > 9:
            raise ValueError("JSON exponent magnitude exceeds data/v1 limit")
        exponent = int(exp_digits)
        if exponent > 1_000_000:
            raise ValueError("JSON exponent magnitude exceeds data/v1 limit")
        if exp_negative:
            exponent = -exponent

    if index != len(text):
        raise ValueError("trailing characters in JSON number")

    digits = (integer + fraction).lstrip("0")
    if not digits:
        return "0"

    scale = exponent - len(fraction)
    trailing = len(digits) - len(digits.rstrip("0"))
    if trailing:
        digits = digits[:-trailing]
        scale += trailing

    scientific_exponent = scale + len(digits) - 1
    sign = "-" if negative else ""

    if scientific_exponent >= 21 or scientific_exponent <= -7:
        coefficient = digits[0]
        if len(digits) > 1:
            coefficient += "." + digits[1:]
        return f"{sign}{coefficient}e{scientific_exponent}"

    decimal_position = len(digits) + scale
    if decimal_position <= 0:
        body = "0." + ("0" * -decimal_position) + digits
    elif decimal_position >= len(digits):
        body = digits + ("0" * (decimal_position - len(digits)))
    else:
        body = digits[:decimal_position] + "." + digits[decimal_position:]
    return sign + body


class _Parser:
    __slots__ = ("text", "limits", "length", "index", "nodes")

    def __init__(self, text: str, limits: Limits) -> None:
        self.text = text
        self.limits = limits
        self.length = len(text)
        self.index = 0
        self.nodes = 0

    def error(self, code: str, message: str, offset: int | None = None) -> DataError:
        character_offset = self.index if offset is None else offset
        byte_offset = len(self.text[:character_offset].encode("utf-8"))
        return DataError(code, message, byte_offset)

    def parse(self) -> JsonValue:
        self._skip_space()
        value = self._value(1)
        self._skip_space()
        if self.index != self.length:
            raise self.error("KS3605", "trailing data after JSON value")
        return value

    def _node(self, depth: int) -> None:
        if depth > self.limits.max_depth:
            raise self.error(
                "KS3602",
                f"JSON depth exceeds limit {self.limits.max_depth}",
            )
        self.nodes += 1
        if self.nodes > self.limits.max_nodes:
            raise self.error(
                "KS3603",
                f"JSON node count exceeds limit {self.limits.max_nodes}",
            )

    def _skip_space(self) -> None:
        while self.index < self.length and self.text[self.index] in " \t\r\n":
            self.index += 1

    def _value(self, depth: int) -> JsonValue:
        self._node(depth)
        if self.index >= self.length:
            raise self.error("KS3605", "unexpected end of JSON input")
        char = self.text[self.index]
        if char == '"':
            return self._string()
        if char == "{":
            return self._object(depth)
        if char == "[":
            return self._array(depth)
        if char == "t" and self.text.startswith("true", self.index):
            self.index += 4
            return True
        if char == "f" and self.text.startswith("false", self.index):
            self.index += 5
            return False
        if char == "n" and self.text.startswith("null", self.index):
            self.index += 4
            return None
        if char == "-" or _is_ascii_digit(char):
            return self._number()
        raise self.error("KS3605", f"unexpected character {char!r}")

    def _array(self, depth: int) -> list[JsonValue]:
        self.index += 1
        items: list[JsonValue] = []
        self._skip_space()
        if self.index < self.length and self.text[self.index] == "]":
            self.index += 1
            return items
        while True:
            items.append(self._value(depth + 1))
            self._skip_space()
            if self.index >= self.length:
                raise self.error("KS3605", "unterminated JSON array")
            char = self.text[self.index]
            self.index += 1
            if char == "]":
                return items
            if char != ",":
                raise self.error("KS3605", "expected ',' or ']' in JSON array", self.index - 1)
            self._skip_space()

    def _object(self, depth: int) -> dict[str, JsonValue]:
        self.index += 1
        result: dict[str, JsonValue] = {}
        self._skip_space()
        if self.index < self.length and self.text[self.index] == "}":
            self.index += 1
            return result
        while True:
            if self.index >= self.length or self.text[self.index] != '"':
                raise self.error("KS3605", "JSON object key must be a string")
            key_offset = self.index
            key = self._string()
            if key in result:
                raise self.error("KS3604", f"duplicate JSON object key {key!r}", key_offset)
            self._skip_space()
            if self.index >= self.length or self.text[self.index] != ":":
                raise self.error("KS3605", "expected ':' after JSON object key")
            self.index += 1
            self._skip_space()
            result[key] = self._value(depth + 1)
            self._skip_space()
            if self.index >= self.length:
                raise self.error("KS3605", "unterminated JSON object")
            char = self.text[self.index]
            self.index += 1
            if char == "}":
                return result
            if char != ",":
                raise self.error("KS3605", "expected ',' or '}' in JSON object", self.index - 1)
            self._skip_space()

    def _string(self) -> str:
        self.index += 1
        chunks: list[str] = []
        start = self.index
        while self.index < self.length:
            char = self.text[self.index]
            if char == '"':
                chunks.append(self.text[start:self.index])
                self.index += 1
                return "".join(chunks)
            if char == "\\":
                chunks.append(self.text[start:self.index])
                self.index += 1
                if self.index >= self.length:
                    raise self.error("KS3605", "unterminated escape in JSON string")
                escape = self.text[self.index]
                self.index += 1
                simple = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                if escape in simple:
                    chunks.append(simple[escape])
                elif escape == "u":
                    chunks.append(self._unicode_escape())
                else:
                    raise self.error("KS3605", f"invalid JSON escape \\{escape}", self.index - 2)
                start = self.index
                continue
            if ord(char) < 0x20:
                raise self.error("KS3605", "unescaped control character in JSON string")
            if 0xD800 <= ord(char) <= 0xDFFF:
                raise self.error("KS3605", "surrogate code point is not valid UTF-8 JSON")
            self.index += 1
        raise self.error("KS3605", "unterminated JSON string")

    def _unicode_escape(self) -> str:
        if self.index + 4 > self.length:
            raise self.error("KS3605", "short \\u escape in JSON string")
        first_text = self.text[self.index:self.index + 4]
        if any(char not in _HEX for char in first_text):
            raise self.error("KS3605", "invalid hex digit in \\u escape")
        self.index += 4
        first = int(first_text, 16)
        if 0xDC00 <= first <= 0xDFFF:
            raise self.error("KS3605", "lone low surrogate in JSON string", self.index - 4)
        if not 0xD800 <= first <= 0xDBFF:
            return chr(first)
        if self.index + 6 > self.length or self.text[self.index:self.index + 2] != "\\u":
            raise self.error("KS3605", "high surrogate requires a low surrogate", self.index - 4)
        self.index += 2
        second_text = self.text[self.index:self.index + 4]
        if any(char not in _HEX for char in second_text):
            raise self.error("KS3605", "invalid low-surrogate escape")
        self.index += 4
        second = int(second_text, 16)
        if not 0xDC00 <= second <= 0xDFFF:
            raise self.error("KS3605", "high surrogate requires a low surrogate", self.index - 4)
        codepoint = 0x10000 + ((first - 0xD800) << 10) + (second - 0xDC00)
        return chr(codepoint)

    def _number(self) -> Number:
        start = self.index
        if self.text[self.index] == "-":
            self.index += 1
        if self.index >= self.length:
            raise self.error("KS3605", "missing digits in JSON number")
        if self.text[self.index] == "0":
            self.index += 1
            if self.index < self.length and _is_ascii_digit(self.text[self.index]):
                raise self.error("KS3605", "leading zero in JSON number")
        elif "1" <= self.text[self.index] <= "9":
            while self.index < self.length and _is_ascii_digit(self.text[self.index]):
                self.index += 1
        else:
            raise self.error("KS3605", "invalid integer part in JSON number")
        if self.index < self.length and self.text[self.index] == ".":
            self.index += 1
            fraction_start = self.index
            while self.index < self.length and _is_ascii_digit(self.text[self.index]):
                self.index += 1
            if self.index == fraction_start:
                raise self.error("KS3605", "fraction requires at least one digit")
        if self.index < self.length and self.text[self.index] in "eE":
            self.index += 1
            if self.index < self.length and self.text[self.index] in "+-":
                self.index += 1
            exponent_start = self.index
            while self.index < self.length and _is_ascii_digit(self.text[self.index]):
                self.index += 1
            if self.index == exponent_start:
                raise self.error("KS3605", "exponent requires at least one digit")
        raw = self.text[start:self.index]
        try:
            return Number(canonical_number(raw))
        except ValueError as error:
            raise self.error("KS3605", str(error), start) from error


def decode(text: str, limits: Limits = DEFAULT_LIMITS) -> JsonValue:
    """Decode one bounded JSON value without host-float conversion."""
    limits.validate()
    if not isinstance(text, str):
        raise TypeError("decode expects a String")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise DataError("KS3605", "input contains a surrogate code point", error.start) from error
    if size > limits.max_input_bytes:
        raise DataError(
            "KS3601",
            f"JSON input bytes exceed limit {limits.max_input_bytes}",
            0,
        )
    return _Parser(text, limits).parse()


class _Writer:
    __slots__ = ("limits", "parts", "size", "nodes")

    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.parts: list[str] = []
        self.size = 0
        self.nodes = 0

    def add(self, text: str) -> None:
        added = len(text.encode("utf-8"))
        if self.size + added > self.limits.max_output_bytes:
            raise DataError(
                "KS3607",
                f"JSON output bytes exceed limit {self.limits.max_output_bytes}",
                self.size,
            )
        self.parts.append(text)
        self.size += added

    def value(self, value: JsonValue, depth: int) -> None:
        if depth > self.limits.max_depth:
            raise DataError(
                "KS3602",
                f"JSON depth exceeds limit {self.limits.max_depth}",
                self.size,
            )
        self.nodes += 1
        if self.nodes > self.limits.max_nodes:
            raise DataError(
                "KS3603",
                f"JSON node count exceeds limit {self.limits.max_nodes}",
                self.size,
            )
        if value is None:
            self.add("null")
        elif type(value) is bool:
            self.add("true" if value else "false")
        elif isinstance(value, str):
            self.string(value)
        elif isinstance(value, Number):
            self.add(value.text)
        elif isinstance(value, list):
            self.add("[")
            for index, item in enumerate(value):
                if index:
                    self.add(",")
                self.value(item, depth + 1)
            self.add("]")
        elif isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise DataError("KS3608", "JSON object keys must be String", self.size)
            self.add("{")
            for index, key in enumerate(sorted(value)):
                if index:
                    self.add(",")
                self.string(key)
                self.add(":")
                self.value(value[key], depth + 1)
            self.add("}")
        else:
            raise DataError(
                "KS3608",
                f"value of type {type(value).__name__} is not data/v1 encodable",
                self.size,
            )

    def string(self, value: str) -> None:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise DataError("KS3608", "string contains a surrogate code point", self.size) from error
        self.add('"')
        start = 0
        for index, char in enumerate(value):
            replacement: str | None = None
            if char == '"':
                replacement = '\\"'
            elif char == "\\":
                replacement = "\\\\"
            elif char == "\b":
                replacement = "\\b"
            elif char == "\f":
                replacement = "\\f"
            elif char == "\n":
                replacement = "\\n"
            elif char == "\r":
                replacement = "\\r"
            elif char == "\t":
                replacement = "\\t"
            elif ord(char) < 0x20:
                replacement = f"\\u{ord(char):04x}"
            if replacement is None:
                continue
            if start < index:
                self.add(value[start:index])
            self.add(replacement)
            start = index + 1
        if start < len(value):
            self.add(value[start:])
        self.add('"')


def encode(value: JsonValue, limits: Limits = DEFAULT_LIMITS) -> str:
    """Encode a value with canonical object ordering and exact numbers."""
    limits.validate()
    writer = _Writer(limits)
    writer.value(value, 1)
    return "".join(writer.parts)
