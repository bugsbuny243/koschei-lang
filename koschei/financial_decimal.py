"""Exact fixed-scale arithmetic for Koschei financial workloads.

The representation is intentionally boring: one signed int64 atom count plus an
explicit decimal scale.  No host floating-point value is accepted or produced.
Addition, subtraction and comparison are exact and need equal scales.
Multiplication, division and rescaling name their result scale and one of
:data:`ROUNDING_MODES`; the exact result is rounded once, in integers, and an
atom count outside int64 is an error rather than a wrapped value.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
MAX_SCALE = 18
_DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
ROUNDING_MODES = ("down", "up", "floor", "ceiling", "half_up", "half_down", "half_even")
ROUNDING_MESSAGE = (
    "KS3801: unknown rounding mode; use down, up, floor, ceiling, half_up, "
    "half_down or half_even"
)
DIVISION_BY_ZERO_MESSAGE = "KS3807: decimal division by zero"
TEXT_TYPE_MESSAGE = "KS3801: decimal() expects canonical String input"
TEXT_MESSAGE = (
    "KS3801: invalid decimal text; exponent, whitespace, plus sign and "
    "non-canonical leading zeroes are forbidden"
)
FRACTION_MESSAGE = (
    "KS3801: decimal input has more fractional digits than the declared scale; "
    "implicit rounding is forbidden"
)
SCALE_TYPE_MESSAGE = "KS3801: decimal scale must be Int"
SCALE_MESSAGE = f"KS3801: decimal scale must be 0..{MAX_SCALE}"
DECIMAL_TYPE_MESSAGE = "KS3801: operation expects Decimal values"
SCALES_DIFFER_MESSAGE = "KS3802: decimal scales differ; implicit rescaling is forbidden"
ATOMS_MESSAGE = "KS3803: decimal atoms overflow signed int64"
OVERFLOW_MESSAGE = "KS3803: decimal {operation} overflow"
# Neither int64 bound has more than 19 digits; longer text is refused before
# it is converted, so no host conversion limit can answer instead.
_MAX_ATOM_DIGITS = 19


class FinancialDecimalError(ValueError):
    """A deterministic, user-visible decimal contract failure."""


@dataclass(frozen=True, slots=True)
class DecimalValue:
    atoms: int
    scale: int

    def __post_init__(self) -> None:
        if isinstance(self.atoms, bool) or not isinstance(self.atoms, int):
            raise TypeError("decimal atoms must be an integer")
        if isinstance(self.scale, bool) or not isinstance(self.scale, int):
            raise TypeError("decimal scale must be an integer")
        if not INT64_MIN <= self.atoms <= INT64_MAX:
            raise ValueError("decimal atoms exceed signed int64")
        if not 0 <= self.scale <= MAX_SCALE:
            raise ValueError(f"decimal scale must be 0..{MAX_SCALE}")


def parse_decimal(raw: str, scale: int) -> DecimalValue:
    if not isinstance(raw, str):
        raise FinancialDecimalError(TEXT_TYPE_MESSAGE)
    _require_scale(scale)
    if not _DECIMAL_RE.fullmatch(raw):
        raise FinancialDecimalError(TEXT_MESSAGE)

    negative = raw.startswith("-")
    unsigned = raw[1:] if negative else raw
    if "." in unsigned:
        whole, fraction = unsigned.split(".", 1)
    else:
        whole, fraction = unsigned, ""
    if len(fraction) > scale:
        raise FinancialDecimalError(FRACTION_MESSAGE)

    digits = (whole + fraction + ("0" * (scale - len(fraction)))).lstrip("0")
    if len(digits) > _MAX_ATOM_DIGITS:
        raise FinancialDecimalError(ATOMS_MESSAGE)
    atoms = int(digits or "0")
    if negative:
        atoms = -atoms
    if not INT64_MIN <= atoms <= INT64_MAX:
        raise FinancialDecimalError(ATOMS_MESSAGE)
    return DecimalValue(atoms, scale)


def decimal_text(value: DecimalValue) -> str:
    value = _require_decimal(value)
    negative = value.atoms < 0
    digits = str(value.atoms)
    if negative:
        digits = digits[1:]
    if value.scale == 0:
        rendered = digits
    else:
        digits = digits.rjust(value.scale + 1, "0")
        rendered = digits[:-value.scale] + "." + digits[-value.scale:]
    if negative and value.atoms != 0:
        return "-" + rendered
    return rendered


def add_decimal(left: DecimalValue, right: DecimalValue) -> DecimalValue:
    left, right = _same_scale(left, right)
    result = left.atoms + right.atoms
    if not INT64_MIN <= result <= INT64_MAX:
        raise FinancialDecimalError(OVERFLOW_MESSAGE.format(operation="addition"))
    return DecimalValue(result, left.scale)


def sub_decimal(left: DecimalValue, right: DecimalValue) -> DecimalValue:
    left, right = _same_scale(left, right)
    result = left.atoms - right.atoms
    if not INT64_MIN <= result <= INT64_MAX:
        raise FinancialDecimalError(OVERFLOW_MESSAGE.format(operation="subtraction"))
    return DecimalValue(result, left.scale)


def mul_decimal(left: DecimalValue, right: DecimalValue, scale: int, mode: str) -> DecimalValue:
    """``left * right`` at ``scale``, rounded once by ``mode``."""

    left, right = _require_decimal(left), _require_decimal(right)
    return _scaled(left.atoms * right.atoms, left.scale + right.scale, 1, scale, mode, "multiplication")


def div_decimal(left: DecimalValue, right: DecimalValue, scale: int, mode: str) -> DecimalValue:
    """``left / right`` at ``scale``, rounded once by ``mode``."""

    left, right = _require_decimal(left), _require_decimal(right)
    _require_scale(scale)
    _require_mode(mode)
    if right.atoms == 0:
        raise FinancialDecimalError(DIVISION_BY_ZERO_MESSAGE)
    # (l / 10^ls) / (r / 10^rs) as atoms of 10^-scale: l * 10^(rs + scale) / (r * 10^ls).
    return _scaled(left.atoms * 10**right.scale, 0, right.atoms * 10**left.scale, scale, mode, "division")


def rescale_decimal(value: DecimalValue, scale: int, mode: str) -> DecimalValue:
    """``value`` at another scale, rounded once by ``mode`` when it shrinks."""

    value = _require_decimal(value)
    return _scaled(value.atoms, value.scale, 1, scale, mode, "rescale")


def _scaled(numerator: int, from_scale: int, denominator: int, scale: int, mode: str, operation: str) -> DecimalValue:
    """``numerator / denominator`` atoms of 10^-from_scale as atoms of 10^-scale."""

    _require_scale(scale)
    _require_mode(mode)
    if scale >= from_scale:
        numerator *= 10 ** (scale - from_scale)
    else:
        denominator *= 10 ** (from_scale - scale)
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    atoms = _round_quotient(numerator, denominator, mode)
    if not INT64_MIN <= atoms <= INT64_MAX:
        raise FinancialDecimalError(OVERFLOW_MESSAGE.format(operation=operation))
    return DecimalValue(atoms, scale)


def _round_quotient(numerator: int, denominator: int, mode: str) -> int:
    """``numerator / denominator`` (denominator > 0) rounded to an integer."""

    negative = numerator < 0
    quotient, remainder = divmod(abs(numerator), denominator)
    if remainder:
        twice = 2 * remainder
        if mode == "up":
            quotient += 1
        elif mode == "floor":
            quotient += negative
        elif mode == "ceiling":
            quotient += not negative
        elif mode == "half_up":
            quotient += twice >= denominator
        elif mode == "half_down":
            quotient += twice > denominator
        elif mode == "half_even":
            quotient += twice > denominator or (twice == denominator and quotient % 2 == 1)
    return -quotient if negative else quotient


def _require_mode(mode: str) -> None:
    if not isinstance(mode, str) or mode not in ROUNDING_MODES:
        raise FinancialDecimalError(ROUNDING_MESSAGE)


def compare_decimal(left: DecimalValue, right: DecimalValue) -> int:
    left, right = _same_scale(left, right)
    return (left.atoms > right.atoms) - (left.atoms < right.atoms)


def _same_scale(
    left: DecimalValue, right: DecimalValue
) -> tuple[DecimalValue, DecimalValue]:
    left = _require_decimal(left)
    right = _require_decimal(right)
    if left.scale != right.scale:
        raise FinancialDecimalError(SCALES_DIFFER_MESSAGE)
    return left, right


def _require_decimal(value: DecimalValue) -> DecimalValue:
    if not isinstance(value, DecimalValue):
        raise FinancialDecimalError(DECIMAL_TYPE_MESSAGE)
    return value


def _require_scale(scale: int) -> None:
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise FinancialDecimalError(SCALE_TYPE_MESSAGE)
    if not 0 <= scale <= MAX_SCALE:
        raise FinancialDecimalError(SCALE_MESSAGE)
