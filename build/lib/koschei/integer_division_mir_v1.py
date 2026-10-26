"""Direct-MIR alignment for Koschei's checked integer division contract.

Direct MIR v1 deliberately admits only division sites whose denominator is a
safe compile-time constant. The bootstrap language can represent division
failure as Error, but the direct executor does not yet re-check every declared
function return type. Refusing dynamic divisors prevents that incomplete runtime
contract from turning a fallible arithmetic edge into an incorrectly admitted
non-fallible path.
"""

from __future__ import annotations

from . import mir_native_runtime as _mir
from .semantic import INT_MIN

_INSTALLED = False
_ORIGINAL_BINARY = None
_ORIGINAL_INSPECT_SUPPORT = None


def _division_reasons(mir) -> tuple[str, ...]:
    reasons: list[str] = []
    for module in mir.in_dependency_order():
        for function in module.functions:
            definitions = _mir._definitions(function)
            for block in function.blocks:
                for instruction in block.instructions:
                    if not (
                        isinstance(instruction, _mir.MirBinary)
                        and instruction.operator == "/"
                    ):
                        continue

                    right = definitions.get(instruction.right)
                    if not isinstance(right, _mir.MirConst):
                        reasons.append(
                            f"{module.name}.{function.name}: direct-MIR division "
                            "requires a compile-time denominator"
                        )
                        continue

                    divisor = right.value
                    if isinstance(divisor, bool) or not isinstance(divisor, (int, float)):
                        reasons.append(
                            f"{module.name}.{function.name}: direct-MIR division "
                            "denominator is not numeric"
                        )
                        continue
                    if divisor == 0:
                        reasons.append(
                            f"{module.name}.{function.name}: direct-MIR division "
                            "denominator may not be zero"
                        )
                        continue

                    if type(divisor) is int and divisor == -1:
                        left = definitions.get(instruction.left)
                        if not (
                            isinstance(left, _mir.MirConst)
                            and type(left.value) is int
                            and left.value != INT_MIN
                        ):
                            reasons.append(
                                f"{module.name}.{function.name}: direct-MIR Int division "
                                "by -1 requires a proven non-INT_MIN numerator"
                            )
    return tuple(reasons)


def _inspect_support(mir):
    report = _ORIGINAL_INSPECT_SUPPORT(mir)
    reasons = tuple(dict.fromkeys((*report.reasons, *_division_reasons(mir))))
    return _mir.MirNativeSupport(not reasons, reasons)


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
    global _INSTALLED, _ORIGINAL_BINARY, _ORIGINAL_INSPECT_SUPPORT
    if _INSTALLED:
        return
    _mir._SUPPORTED_BINARY = frozenset(set(_mir._SUPPORTED_BINARY) | {"/"})

    _ORIGINAL_BINARY = _mir._binary
    _mir._binary = _binary

    _ORIGINAL_INSPECT_SUPPORT = _mir.inspect_native_mir_support
    _mir.inspect_native_mir_support = _inspect_support

    _INSTALLED = True
