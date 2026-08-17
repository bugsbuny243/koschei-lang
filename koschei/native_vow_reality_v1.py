"""Koschei-native Vow Reality v1.

A vow is not try/catch, assert, exception, or statement-order control flow. It is
an admission invariant attached to a closed decision/value reality. Every vow
names an already-reachable truth witness. The reality is admitted only when all
vows are true.

Surface:
    witness gate truth yes
    witness accepted glyphs 2 ok
    witness rejected glyphs 2 no
    witness result settle gate accepted rejected
    vow gate
    resolve result

Vow clauses are source-order independent and never produce values. They constrain
whether the surrounding reality may exist at all.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import native_decision_realities_v1 as decision
from . import native_value_domains_v1 as base

VOW = "vow"
MAX_VOWS = 256


class NativeVowRealityError(decision.NativeDecisionRealityError):
    pass


@dataclass(frozen=True, slots=True)
class NativeVowRealityCheckV1:
    decision: decision.NativeDecisionRealityCheck
    vows: tuple[str, ...]

    @property
    def value(self):
        return self.decision.value


def _fail(code: str, message: str, line: int = 1) -> None:
    raise NativeVowRealityError(code, message, line, 1)


def _split_vows(source: str) -> tuple[str, tuple[tuple[str, int], ...]]:
    try:
        lines = base._canonical_lines(source)
    except base.NativeValueDomainError as error:
        raise NativeVowRealityError(error.code, error.message, error.line, error.column) from error

    ordinary: list[str] = []
    vows: list[tuple[str, int]] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, 1):
        tokens = line.split(" ")
        if tokens[0] != VOW:
            ordinary.append(line)
            continue
        if len(tokens) != 2:
            _fail("KW1001", "vow form is exactly: vow <truth-witness>", number)
        try:
            name = decision._decision_name(tokens[1], line=number)
        except decision.NativeDecisionRealityError as error:
            raise NativeVowRealityError(error.code, error.message, error.line, error.column) from error
        if name in seen:
            _fail("KW1101", f"duplicate vow for witness {name!r}", number)
        seen.add(name)
        vows.append((name, number))
        if len(vows) > MAX_VOWS:
            _fail("KW1102", f"vow reality exceeds {MAX_VOWS} invariants", number)

    if not vows:
        _fail("KW1100", "vow reality requires at least one vow")
    if not ordinary:
        _fail("KW1103", "vow reality has no executable value graph")
    return "\n".join(ordinary) + "\n", tuple(vows)


def check_native_vow_reality_v1(source: str) -> NativeVowRealityCheckV1:
    stripped, vows = _split_vows(source)
    try:
        checked = decision.check_native_decision_reality(stripped)
    except decision.NativeDecisionRealityError as error:
        raise NativeVowRealityError(error.code, error.message, error.line, error.column) from error

    reachable = set(checked.structural_order)
    for name, line in vows:
        if name not in checked.values:
            _fail("KW1201", f"vow references unknown witness {name!r}", line)
        if name not in reachable:
            _fail("KW1202", f"vow witness {name!r} is outside resolved reality", line)
        value = checked.values[name]
        if value.domain != base.TRUTH:
            _fail("KW1401", "vow requires a truth witness and forbids coercion", line)
        if value.value is not True:
            _fail("KW1402", f"vow {name!r} is not satisfied", line)

    return NativeVowRealityCheckV1(checked, tuple(name for name, _ in vows))
