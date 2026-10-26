"""Koschei-native Signal Reality v1.

A signal is an authority-injected runtime fact, not a function parameter, stdin
read, environment lookup, global variable, or implicit host callback. Source names
only a local signal slot; the host supplies the exact canonical value through a
separate binding map.

Surface:
    witness price signal 0
    witness fee 2
    witness total sum price fee
    resolve total

Signal slots are unique, bounded, source-order independent and carry no authority
by themselves. Missing, duplicate, unknown or non-canonical bindings fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from . import native_value_domains_v1 as base
from .semantic import INT_MAX, INT_MIN

SIGNAL = "signal"
MAX_SIGNALS = 256
MAX_SIGNAL_SLOT = 65535


class NativeSignalRealityError(base.NativeValueDomainError):
    pass


@dataclass(frozen=True, slots=True)
class SignalWitness:
    name: str
    operation: str | None
    atoms: tuple[str, ...]
    literal: base.NativeValue | None
    signal_slot: int | None
    line: int


@dataclass(frozen=True, slots=True)
class SignalGraph:
    witnesses: tuple[SignalWitness, ...]
    resolve: str

    def by_name(self) -> dict[str, SignalWitness]:
        return {item.name: item for item in self.witnesses}


def _fail(code: str, message: str, line: int = 1) -> None:
    raise NativeSignalRealityError(code, message, line, 1)


def _slot(token: str, line: int) -> int:
    if not token.isascii() or not token.isdigit():
        _fail("KSIG1200", "signal slot must be canonical unsigned decimal", line)
    if len(token) > 1 and token.startswith("0"):
        _fail("KSIG1200", "signal slot has a leading-zero alias", line)
    if len(token) > 5:
        _fail("KSIG1200", "signal slot exceeds v1 range", line)
    value = int(token)
    if value > MAX_SIGNAL_SLOT:
        _fail("KSIG1200", "signal slot exceeds v1 range", line)
    return value


def _atom_token(atom: base.ValueAtom, line: int) -> tuple[str, base.NativeValue | None]:
    if atom.literal is not None:
        return "", atom.literal
    if atom.witness is None:
        _fail("KSIG1005", "non-canonical signal atom", line)
    return atom.witness, None


def parse_native_signal_reality_v1(source: str) -> SignalGraph:
    try:
        lines = base._canonical_lines(source)
    except base.NativeValueDomainError as error:
        raise NativeSignalRealityError(error.code, error.message, error.line, error.column) from error

    witnesses: list[SignalWitness] = []
    seen_names: set[str] = set()
    seen_slots: set[int] = set()
    resolve: str | None = None

    for number, line in enumerate(lines, 1):
        tokens = line.split(" ")
        if tokens[0] == "resolve":
            if len(tokens) != 2 or resolve is not None:
                _fail("KSIG1100", "signal reality requires exactly one resolve", number)
            try:
                resolve = base._name(tokens[1], line=number)
            except base.NativeValueDomainError as error:
                raise NativeSignalRealityError(error.code, error.message, error.line, error.column) from error
            continue

        if tokens[0] != "witness" or len(tokens) < 3:
            _fail("KSIG1000", "unknown native signal clause", number)
        try:
            name = base._name(tokens[1], line=number)
        except base.NativeValueDomainError as error:
            raise NativeSignalRealityError(error.code, error.message, error.line, error.column) from error
        if name in seen_names:
            _fail("KSIG1101", f"duplicate witness identity {name!r}", number)
        seen_names.add(name)
        body = tokens[2:]

        if body[0] == SIGNAL:
            if len(body) != 2:
                _fail("KSIG1201", "signal form is exactly: signal <slot>", number)
            slot = _slot(body[1], number)
            if slot in seen_slots:
                _fail("KSIG1202", "duplicate signal slot", number)
            seen_slots.add(slot)
            if len(seen_slots) > MAX_SIGNALS:
                _fail("KSIG1203", f"signal reality exceeds {MAX_SIGNALS} slots", number)
            witnesses.append(SignalWitness(name, SIGNAL, (), None, slot, number))
            continue

        try:
            term = base._term(body, line=number)
        except base.NativeValueDomainError as error:
            raise NativeSignalRealityError(error.code, error.message, error.line, error.column) from error
        if term.operation is None:
            atom = term.atoms[0]
            token, literal = _atom_token(atom, number)
            witnesses.append(SignalWitness(name, None, (token,) if token else (), literal, None, number))
        else:
            args: list[str] = []
            literal_atoms: list[base.NativeValue] = []
            # v1 keeps operation inputs witness-bound so runtime signal influence is
            # explicit in the graph instead of hidden inside mixed literal operands.
            for atom in term.atoms:
                if atom.witness is None:
                    literal_atoms.append(atom.literal)  # type: ignore[arg-type]
                else:
                    args.append(atom.witness)
            if literal_atoms:
                _fail("KSIG1204", "signal v1 operations require witness inputs; bind literals as witnesses", number)
            witnesses.append(SignalWitness(name, term.operation, tuple(args), None, None, number))

    if not witnesses:
        _fail("KSIG1102", "signal reality must contain witnesses")
    if not seen_slots:
        _fail("KSIG1103", "signal reality requires at least one signal")
    if resolve is None:
        _fail("KSIG1100", "signal reality requires exactly one resolve")
    if resolve not in seen_names:
        _fail("KSIG1104", "resolve references unknown witness")
    return SignalGraph(tuple(witnesses), resolve)


def _dependencies(witness: SignalWitness) -> tuple[str, ...]:
    if witness.operation == SIGNAL or witness.literal is not None:
        return ()
    return tuple(witness.atoms)


def dependency_order_signal_reality_v1(graph: SignalGraph) -> tuple[str, ...]:
    by_name = graph.by_name()
    state: dict[str, int] = {}
    reachable: set[str] = set()
    order: list[str] = []
    stack: list[tuple[str, int]] = [(graph.resolve, 0)]
    while stack:
        name, index = stack[-1]
        witness = by_name.get(name)
        if witness is None:
            _fail("KSIG1105", f"unknown dependency {name!r}")
        if state.get(name, 0) == 0:
            state[name] = 1
            reachable.add(name)
        deps = _dependencies(witness)
        if index < len(deps):
            dep = deps[index]
            stack[-1] = (name, index + 1)
            if dep not in by_name:
                _fail("KSIG1105", f"witness {name!r} references unknown witness {dep!r}", witness.line)
            mark = state.get(dep, 0)
            if mark == 1:
                _fail("KSIG1106", "signal reality contains a dependency cycle", witness.line)
            if mark == 0:
                stack.append((dep, 0))
            continue
        stack.pop()
        state[name] = 2
        order.append(name)
    dormant = sorted(set(by_name) - reachable)
    if dormant:
        _fail("KSIG1107", "signal reality contains dormant witnesses: " + ", ".join(dormant))
    return tuple(order)


def _canonical_binding(value: object, slot: int) -> base.NativeValue:
    if not isinstance(value, base.NativeValue):
        _fail("KSIG1300", f"signal slot {slot} requires canonical NativeValue")
    if value.domain == base.WHOLE:
        if not isinstance(value.value, int) or isinstance(value.value, bool) or not INT_MIN <= value.value <= INT_MAX:
            _fail("KSIG1301", f"signal slot {slot} carries non-canonical whole")
    elif value.domain == base.TRUTH:
        if not isinstance(value.value, bool):
            _fail("KSIG1301", f"signal slot {slot} carries non-canonical truth")
    elif value.domain == base.GLYPHS:
        if not isinstance(value.value, str) or len(value.value.encode("utf-8")) > base.MAX_GLYPHS_RESULT_BYTES:
            _fail("KSIG1301", f"signal slot {slot} carries non-canonical glyphs")
    else:
        _fail("KSIG1301", f"signal slot {slot} carries unsupported domain")
    return value


def evaluate_native_signal_reality_v1(source: str, bindings: Mapping[int, base.NativeValue]) -> base.NativeValue:
    graph = parse_native_signal_reality_v1(source)
    if not isinstance(bindings, Mapping):
        _fail("KSIG1300", "signal bindings must be a mapping")
    required = {w.signal_slot for w in graph.witnesses if w.operation == SIGNAL}
    supplied = set(bindings.keys())
    if required != supplied:
        missing = sorted(required - supplied)
        extra = sorted(supplied - required)
        _fail("KSIG1302", f"signal binding set mismatch missing={missing} extra={extra}")

    values: dict[str, base.NativeValue] = {}
    for name in dependency_order_signal_reality_v1(graph):
        witness = graph.by_name()[name]
        if witness.operation == SIGNAL:
            assert witness.signal_slot is not None
            values[name] = _canonical_binding(bindings[witness.signal_slot], witness.signal_slot)
            continue
        if witness.literal is not None:
            values[name] = witness.literal
            continue
        if witness.operation is None:
            values[name] = values[witness.atoms[0]]
            continue

        left = values[witness.atoms[0]]
        right = values[witness.atoms[1]]
        op = witness.operation
        if op in base._NUMERIC_OPS:
            if left.domain != base.WHOLE or right.domain != base.WHOLE:
                _fail("KSIG1401", f"{op} requires whole/whole and forbids coercion", witness.line)
            a, b = int(left.value), int(right.value)
            result = a + b if op == "sum" else a - b if op == "difference" else a * b
            if not INT_MIN <= result <= INT_MAX:
                _fail("KSIG1402", f"{op} exceeds signed Int64 reality", witness.line)
            values[name] = base.NativeValue(base.WHOLE, result)
        elif op == "same":
            if left.domain != right.domain:
                _fail("KSIG1403", "same forbids cross-domain comparison", witness.line)
            values[name] = base.NativeValue(base.TRUTH, left.value == right.value)
        elif op == "merge":
            if left.domain != base.GLYPHS or right.domain != base.GLYPHS:
                _fail("KSIG1404", "merge requires glyphs/glyphs", witness.line)
            merged = str(left.value) + str(right.value)
            if len(merged.encode("utf-8")) > base.MAX_GLYPHS_RESULT_BYTES:
                _fail("KSIG1405", "merged glyphs exceeds result budget", witness.line)
            values[name] = base.NativeValue(base.GLYPHS, merged)
        else:
            _fail("KSIG1406", f"unsupported signal operation {op!r}", witness.line)

    return values[graph.resolve]
