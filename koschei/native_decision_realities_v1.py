"""Koschei-native decision reality over closed value graphs.

`settle` is not statement branching and is not an `if`/`else` rename.  A settle
witness is a graph equation with three inputs:

    witness result settle condition affirmative negative

The condition must be `truth`; both candidate realities must have the same value
domain.  Structural admission validates *both* candidate realities, while the
runtime realization contains only the condition and the selected candidate path.
This distinction is deliberate: future effectful candidates must not inherit a
model that executes both sides merely because both are statically admissible.

V1 remains a closed, pure graph, so candidate validity can be fully proven before
compatibility lowering.  The selected canonical values are materialized below the
frontend boundary exactly as in native value domains v1.
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from . import native_value_domains_v1 as _base
from .ast_nodes import Block, Identifier, LetStatement, Program, ReturnStatement, SourceLocation
from .generic_nodes import GenericFunctionDeclaration
from .semantic import INT_MAX, INT_MIN, SemanticChecker, SemanticReport


SETTLE = "settle"
_DECISION_WORDS = frozenset({SETTLE})


class NativeDecisionRealityError(_base.NativeValueDomainError):
    pass


@dataclass(frozen=True, slots=True)
class NativeDecisionRealityCheck:
    graph: _base.NativeValueGraph
    structural_order: tuple[str, ...]
    active_order: tuple[str, ...]
    values: dict[str, _base.NativeValue]
    value: _base.NativeValue
    lowered: Program
    semantic: SemanticReport


def native_decision_surface_words_v1() -> frozenset[str]:
    return frozenset(set(_base.native_value_surface_words_v1()) | _DECISION_WORDS)


def _fail(code: str, message: str, line: int = 1, column: int = 1) -> None:
    raise NativeDecisionRealityError(code, message, line, column)


def _decision_name(token: str, *, line: int) -> str:
    if token in _DECISION_WORDS:
        _fail("KD1004", f"{token!r} is reserved and cannot be a witness identity", line, 1)
    try:
        return _base._name(token, line=line)
    except _base.NativeValueDomainError as error:
        raise NativeDecisionRealityError(error.code, error.message, error.line, error.column) from error


def _decision_term(tokens: list[str], *, line: int) -> _base.ValueTerm:
    if tokens and tokens[0] == SETTLE:
        if len(tokens) != 4:
            _fail(
                "KD1005",
                "settle requires exactly: settle <truth-witness> <affirmative> <negative>",
                line,
                1,
            )
        return _base.ValueTerm(
            SETTLE,
            tuple(_base._plain_atom(token, line=line) for token in tokens[1:]),
        )
    try:
        return _base._term(tokens, line=line)
    except _base.NativeValueDomainError as error:
        raise NativeDecisionRealityError(error.code, error.message, error.line, error.column) from error


def parse_native_decision_graph(source: str) -> _base.NativeValueGraph:
    """Parse decision graph source without consulting legacy control-flow syntax."""

    try:
        lines = _base._canonical_lines(source)
    except _base.NativeValueDomainError as error:
        raise NativeDecisionRealityError(error.code, error.message, error.line, error.column) from error

    witnesses: list[_base.ValueWitness] = []
    seen: set[str] = set()
    resolve_name: str | None = None
    resolve_location: SourceLocation | None = None

    for line_number, line in enumerate(lines, start=1):
        tokens = line.split(" ")
        head = tokens[0]
        grammar_prefix = line
        if len(tokens) >= 3 and tokens[0] == "witness" and tokens[2] == "glyphs":
            grammar_prefix = " ".join(tokens[:4]) if len(tokens) >= 4 else line
        for symbol in _base._LEGACY_SYMBOLS:
            if symbol in grammar_prefix:
                _fail(
                    "KD1006",
                    f"legacy punctuation {symbol!r} is not native decision grammar",
                    line_number,
                    1,
                )

        if head == "witness":
            if len(tokens) < 3:
                _fail("KD1005", "witness requires identity and term", line_number, 1)
            name = _decision_name(tokens[1], line=line_number)
            if name in seen:
                _fail("KD1101", f"duplicate witness identity {name!r}", line_number, 1)
            seen.add(name)
            witnesses.append(
                _base.ValueWitness(
                    name,
                    _decision_term(tokens[2:], line=line_number),
                    SourceLocation(line_number, 1),
                )
            )
            if len(witnesses) > _base.MAX_VALUE_WITNESSES:
                _fail(
                    "KD1102",
                    f"decision graph exceeds {_base.MAX_VALUE_WITNESSES} witnesses",
                    line_number,
                    1,
                )
            continue

        if head == "resolve":
            if len(tokens) != 2:
                _fail("KD1005", "resolve requires exactly one witness identity", line_number, 1)
            if resolve_name is not None:
                _fail("KD1103", "decision graph must contain exactly one resolve", line_number, 1)
            resolve_name = _decision_name(tokens[1], line=line_number)
            resolve_location = SourceLocation(line_number, 1)
            continue

        if head in _base._LEGACY_WORDS:
            _fail("KD1006", f"legacy grammar word {head!r} is rejected", line_number, 1)
        _fail("KD1005", f"unknown native decision clause {head!r}", line_number, 1)

    if not witnesses:
        _fail("KD1104", "decision graph must contain at least one witness")
    if resolve_name is None or resolve_location is None:
        _fail("KD1103", "decision graph must contain exactly one resolve")

    graph = _base.NativeValueGraph(tuple(witnesses), resolve_name, resolve_location)
    try:
        _base.dependency_order_value_graph(graph)
    except _base.NativeValueDomainError as error:
        raise NativeDecisionRealityError(error.code, error.message, error.line, error.column) from error
    return graph


def _atom_value(atom: _base.ValueAtom, values: dict[str, _base.NativeValue]) -> _base.NativeValue:
    if atom.literal is not None:
        return atom.literal
    assert atom.witness is not None
    return values[atom.witness]


def evaluate_native_decision_graph(
    graph: _base.NativeValueGraph,
) -> dict[str, _base.NativeValue]:
    """Statically validate every candidate reality and compute canonical values."""

    by_name = graph.by_name()
    values: dict[str, _base.NativeValue] = {}
    try:
        order = _base.dependency_order_value_graph(graph)
    except _base.NativeValueDomainError as error:
        raise NativeDecisionRealityError(error.code, error.message, error.line, error.column) from error

    for name in order:
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            value = _atom_value(term.atoms[0], values)
        elif term.operation == SETTLE:
            condition = _atom_value(term.atoms[0], values)
            affirmative = _atom_value(term.atoms[1], values)
            negative = _atom_value(term.atoms[2], values)
            if condition.domain != _base.TRUTH:
                _fail(
                    "KD1401",
                    "settle condition must be truth and cannot coerce another domain",
                    witness.location.line,
                    1,
                )
            if affirmative.domain != negative.domain:
                _fail(
                    "KD1402",
                    "settle candidates must have identical value domains",
                    witness.location.line,
                    1,
                )
            value = affirmative if bool(condition.value) else negative
        else:
            left = _atom_value(term.atoms[0], values)
            right = _atom_value(term.atoms[1], values)
            operation = term.operation
            if operation in _base._NUMERIC_OPS:
                if left.domain != _base.WHOLE or right.domain != _base.WHOLE:
                    _fail(
                        "KD1403",
                        f"{operation} requires whole/whole and forbids coercion",
                        witness.location.line,
                        1,
                    )
                a = int(left.value)
                b = int(right.value)
                if operation == "sum":
                    result = a + b
                elif operation == "difference":
                    result = a - b
                else:
                    result = a * b
                if not INT_MIN <= result <= INT_MAX:
                    _fail(
                        "KD1404",
                        f"{operation} exceeds signed Int64 reality",
                        witness.location.line,
                        1,
                    )
                value = _base.NativeValue(_base.WHOLE, result)
            elif operation == "same":
                if left.domain != right.domain:
                    _fail(
                        "KD1405",
                        "same requires identical value domains and forbids coercion",
                        witness.location.line,
                        1,
                    )
                value = _base.NativeValue(_base.TRUTH, left.value == right.value)
            elif operation == "merge":
                if left.domain != _base.GLYPHS or right.domain != _base.GLYPHS:
                    _fail(
                        "KD1406",
                        "merge requires glyphs/glyphs and forbids textual coercion",
                        witness.location.line,
                        1,
                    )
                merged = unicodedata.normalize("NFC", str(left.value) + str(right.value))
                if len(merged.encode("utf-8")) > _base.MAX_GLYPHS_RESULT_BYTES:
                    _fail(
                        "KD1407",
                        "merged glyphs exceeds result byte budget",
                        witness.location.line,
                        1,
                    )
                value = _base.NativeValue(_base.GLYPHS, merged)
            else:
                _fail(
                    "KD1005",
                    f"unknown decision operation {operation!r}",
                    witness.location.line,
                    1,
                )
        values[name] = value
    return values


def active_order_native_decision_graph(
    graph: _base.NativeValueGraph,
    values: dict[str, _base.NativeValue],
) -> tuple[str, ...]:
    """Return only the dependency reality selected by each settle witness."""

    structural = _base.dependency_order_value_graph(graph)
    by_name = graph.by_name()
    active: set[str] = set()
    stack = [graph.resolve]

    while stack:
        name = stack.pop()
        if name in active:
            continue
        active.add(name)
        witness = by_name[name]
        term = witness.term
        if term.operation == SETTLE:
            condition_atom, affirmative_atom, negative_atom = term.atoms
            condition = _atom_value(condition_atom, values)
            chosen = affirmative_atom if bool(condition.value) else negative_atom
            if condition_atom.witness is not None:
                stack.append(condition_atom.witness)
            if chosen.witness is not None:
                stack.append(chosen.witness)
            continue
        for atom in term.atoms:
            if atom.witness is not None:
                stack.append(atom.witness)

    return tuple(name for name in structural if name in active)


def lower_native_decision_graph(
    graph: _base.NativeValueGraph,
    values: dict[str, _base.NativeValue],
) -> Program:
    """Materialize only the selected runtime reality into compatibility AST."""

    by_name = graph.by_name()
    active_order = active_order_native_decision_graph(graph, values)
    statements = []
    for name in active_order:
        witness = by_name[name]
        value = values[name]
        statements.append(
            LetStatement(
                witness.name,
                False,
                _base._lower_value(value, witness.location),
                witness.location,
                _base._type_ref(value.domain, witness.location),
            )
        )
    statements.append(
        ReturnStatement(
            Identifier(graph.resolve, graph.resolve_location),
            graph.resolve_location,
        )
    )
    resolved = values[graph.resolve]
    origin = GenericFunctionDeclaration(
        name="main",
        parameters=(),
        return_type=_base._type_ref(resolved.domain, SourceLocation(1, 1)),
        body=Block(tuple(statements)),
        location=SourceLocation(1, 1),
        is_pure=True,
        type_parameters=(),
        is_transition=False,
    )
    return Program((origin,))


def check_native_decision_reality(source: str) -> NativeDecisionRealityCheck:
    graph = parse_native_decision_graph(source)
    structural = _base.dependency_order_value_graph(graph)
    values = evaluate_native_decision_graph(graph)
    active = active_order_native_decision_graph(graph, values)
    lowered = lower_native_decision_graph(graph, values)
    semantic = SemanticChecker(lowered).check()
    return NativeDecisionRealityCheck(
        graph=graph,
        structural_order=structural,
        active_order=active,
        values=values,
        value=values[graph.resolve],
        lowered=lowered,
        semantic=semantic,
    )
