"""Exact fixed-scale arithmetic for Koschei financial workloads.

The representation is intentionally boring: one signed int64 atom count plus an
explicit decimal scale.  No host floating-point value is accepted or produced.
Operations that could lose information are not part of this v1 core.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
MAX_SCALE = 18
_DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


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
        raise FinancialDecimalError("KS3801: decimal() expects canonical String input")
    _require_scale(scale)
    if not _DECIMAL_RE.fullmatch(raw):
        raise FinancialDecimalError(
            "KS3801: invalid decimal text; exponent, whitespace, plus sign and "
            "non-canonical leading zeroes are forbidden"
        )

    negative = raw.startswith("-")
    unsigned = raw[1:] if negative else raw
    if "." in unsigned:
        whole, fraction = unsigned.split(".", 1)
    else:
        whole, fraction = unsigned, ""
    if len(fraction) > scale:
        raise FinancialDecimalError(
            "KS3801: decimal input has more fractional digits than the declared scale; "
            "implicit rounding is forbidden"
        )

    digits = whole + fraction + ("0" * (scale - len(fraction)))
    atoms = int(digits)
    if negative:
        atoms = -atoms
    if not INT64_MIN <= atoms <= INT64_MAX:
        raise FinancialDecimalError("KS3803: decimal atoms overflow signed int64")
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
        raise FinancialDecimalError("KS3803: decimal addition overflow")
    return DecimalValue(result, left.scale)


def sub_decimal(left: DecimalValue, right: DecimalValue) -> DecimalValue:
    left, right = _same_scale(left, right)
    result = left.atoms - right.atoms
    if not INT64_MIN <= result <= INT64_MAX:
        raise FinancialDecimalError("KS3803: decimal subtraction overflow")
    return DecimalValue(result, left.scale)


def compare_decimal(left: DecimalValue, right: DecimalValue) -> int:
    left, right = _same_scale(left, right)
    return (left.atoms > right.atoms) - (left.atoms < right.atoms)


def _same_scale(
    left: DecimalValue, right: DecimalValue
) -> tuple[DecimalValue, DecimalValue]:
    left = _require_decimal(left)
    right = _require_decimal(right)
    if left.scale != right.scale:
        raise FinancialDecimalError(
            "KS3802: decimal scales differ; implicit rescaling is forbidden"
        )
    return left, right


def _require_decimal(value: DecimalValue) -> DecimalValue:
    if not isinstance(value, DecimalValue):
        raise FinancialDecimalError("KS3801: operation expects Decimal values")
    return value


def _require_scale(scale: int) -> None:
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise FinancialDecimalError("KS3801: decimal scale must be Int")
    if not 0 <= scale <= MAX_SCALE:
        raise FinancialDecimalError(f"KS3801: decimal scale must be 0..{MAX_SCALE}")
