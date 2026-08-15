"""Direct-MIR alignment for Koschei's checked integer division contract."""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .semantic import INT_MIN

_INSTALLED = False
_ORIGINAL_BINARY = None


def _binary(operator, left, right):
    if operator != "/":
        return _ORIGINAL_BINARY(operator, left, right)

    if right == 0:
        return _mir._ErrorValue("Sıfıra bölme")

    if type(left) is int and type(right) is int:
        if left == INT_MIN and right == -1:
            return _mir._ErrorValue(
                "KS3501: Int taşması: '/' işlemi işaretli 64-bit aralığın dışına çıktı."
            )
        quotient = abs(left) // abs(right)
        return -quotient if (left < 0) != (right < 0) else quotient

    return left / right


def install_integer_division_mir_v1() -> None:
    global _INSTALLED, _ORIGINAL_BINARY
    if _INSTALLED:
        return
    _mir._SUPPORTED_BINARY = frozenset(set(_mir._SUPPORTED_BINARY) | {"/"})
    _ORIGINAL_BINARY = _mir._binary
    _mir._binary = _binary
    _INSTALLED = True
