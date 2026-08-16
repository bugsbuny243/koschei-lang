"""Koschei-native canonical value-domain graph v1.

This frontend extends the closed witness-graph idea without introducing type
statements, structs, enums, classes, variable declarations or implicit coercion.
Every witness resolves to one canonical value domain determined by its term:

    witness amount 40
    witness enabled truth yes
    witness label glyphs 11 hello world
    witness total sum amount 2
    witness caption merge label label
    witness sameamount same amount total
    resolve caption

The source order is still non-semantic. Domains are properties of graph values,
not declarations attached to storage names. Cross-domain operations and implicit
coercions fail closed before the compatibility backend is entered.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .ast_nodes import (
    BinaryExpression,
    Block,
    Identifier,
    LetStatement,
    Literal,
    Program,
    ReturnStatement,
    SourceLocation,
    TypeRef,
)
from .generic_nodes import GenericFunctionDeclaration
from .semantic import INT_MAX, INT_MIN, SemanticChecker, SemanticReport


MAX_VALUE_SOURCE_BYTES = 1 << 20
MAX_VALUE_WITNESSES = 4096
MAX_VALUE_NAME_BYTES = 64
MAX_GLYPHS_LITERAL_BYTES = 1 << 16
MAX_GLYPHS_RESULT_BYTES = 1 << 20
_VALUE_NAME = re.compile(r"^[a-z][a-z0-9]{0,63}$")
_VALUE_WORDS = frozenset(
    {
        "witness",
        "resolve",
        "sum",
        "difference",
        "product",
        "truth",
        "yes",
        "no",
        "glyphs",
        "same",
        "merge",
    }
)
_NUMERIC_OPS = frozenset({"sum", "difference", "product"})
_BINARY_OPS = frozenset({"sum", "difference", "product", "same", "merge"})
_LEGACY_WORDS = frozenset(
    {
        "pure", "stateful", "fn", "let", "mut", "or", "return", "if", "else",
        "while", "for", "in", "break", "continue", "struct", "enum", "match",
        "import", "true", "false", "type", "class", "module", "package",
    }
)
_LEGACY_SYMBOLS = frozenset(
    {
        "(", ")", "{", "}", "[", "]", ",", ":", ".", "=", "+", "-", "*",
        "/", "%", ";", "!", "<", ">", "->", "=>", "==", "!=", "<=", ">=",
        "&&", "||", "::", "@", "#",
    }
)

WHOLE = "whole"
TRUTH = "truth"
GLYPHS = "glyphs"


class NativeValueDomainError(ValueError):
    def __init__(self, code: str, message: str, line: int = 1, column: int = 1) -> None:
        self.code = code
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"{code} [line {line}, column {column}]: {message}")


@dataclass(frozen=True, slots=True)
class NativeValue:
    domain: str
    value: int | bool | str


@dataclass(frozen=True, slots=True)
class ValueAtom:
    literal: NativeValue | None = None
    witness: str | None = None

    def __post_init__(self) -> None:
        if (self.literal is None) == (self.witness is None):
            raise ValueError("value atom must contain exactly one literal or witness reference")


@dataclass(frozen=True, slots=True)
class ValueTerm:
    operation: str | None
    atoms: tuple[ValueAtom, ...]


@dataclass(frozen=True, slots=True)
class ValueWitness:
    name: str
    term: ValueTerm
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class NativeValueGraph:
    witnesses: tuple[ValueWitness, ...]
    resolve: str
    resolve_location: SourceLocation

    def by_name(self) -> dict[str, ValueWitness]:
        return {item.name: item for item in self.witnesses}


@dataclass(frozen=True, slots=True)
class NativeValueDomainCheck:
    graph: NativeValueGraph
    dependency_order: tuple[str, ...]
    values: dict[str, NativeValue]
    value: NativeValue
    lowered: Program
    semantic: SemanticReport


def native_value_surface_words_v1() -> frozenset[str]:
    return _VALUE_WORDS


def _fail(code: str, message: str, line: int = 1, column: int = 1) -> None:
    raise NativeValueDomainError(code, message, line, column)


def _canonical_lines(source: object) -> tuple[str, ...]:
    if not isinstance(source, str):
        _fail("KV1000", "native value source must be text")
    if "\x00" in source:
        _fail("KV1000", "NUL is forbidden in native value source")
    if source != unicodedata.normalize("NFC", source):
        _fail("KV1001", "native value source must be Unicode NFC canonical")
    try:
        payload = source.encode("utf-8")
    except UnicodeEncodeError as error:
        raise NativeValueDomainError("KV1001", "native value source is not valid UTF-8") from error
    if len(payload) > MAX_VALUE_SOURCE_BYTES:
        _fail("KV1002", f"native value source exceeds {MAX_VALUE_SOURCE_BYTES} bytes")
    if "\r" in source or "\t" in source:
        _fail("KV1003", "native value source requires LF and forbids tabs")
    if not source.endswith("\n") or source.endswith("\n\n"):
        _fail("KV1003", "native value source must end in exactly one LF")
    lines = tuple(source[:-1].split("\n"))
    if not lines or any(not line for line in lines):
        _fail("KV1003", "blank clauses are not canonical")
    for number, line in enumerate(lines, start=1):
        if line != line.strip() or "  " in line:
            _fail("KV1003", "clauses forbid indentation, trailing space and repeated spaces", number, 1)
        for char in line:
            code = ord(char)
            if code < 32 or 0x7F <= code <= 0x9F:
                _fail("KV1003", "control characters are forbidden", number, 1)
    return lines


def _name(token: str, *, line: int) -> str:
    if token in _VALUE_WORDS or token in _LEGACY_WORDS:
        _fail("KV1004", f"{token!r} is reserved and cannot be a witness identity", line, 1)
    try:
        encoded = token.encode("ascii")
    except UnicodeEncodeError:
        _fail("KV1004", "witness identities are lowercase ASCII only", line, 1)
    if _VALUE_NAME.fullmatch(token) is None or len(encoded) > MAX_VALUE_NAME_BYTES:
        _fail("KV1004", "witness identity must be 1..64 lowercase ASCII letters/digits", line, 1)
    return token


def _whole(token: str, *, line: int) -> NativeValue | None:
    if not token.isascii() or not token.isdigit():
        return None
    if len(token) > 1 and token.startswith("0"):
        _fail("KV1200", "whole literal has a leading-zero alias", line, 1)
    if len(token) > 19 or (len(token) == 19 and token > str(INT_MAX)):
        _fail("KV1201", "whole literal exceeds signed Int64 reality", line, 1)
    return NativeValue(WHOLE, int(token))


def _plain_atom(token: str, *, line: int) -> ValueAtom:
    number = _whole(token, line=line)
    if number is not None:
        return ValueAtom(literal=number)
    return ValueAtom(witness=_name(token, line=line))


def _glyphs_term(tokens: list[str], *, line: int) -> ValueTerm:
    if len(tokens) < 2:
        _fail("KV1300", "glyphs requires a canonical UTF-8 byte length and payload", line, 1)
    size_token = tokens[1]
    if not size_token.isascii() or not size_token.isdigit():
        _fail("KV1300", "glyphs byte length must be canonical unsigned decimal", line, 1)
    if len(size_token) > 1 and size_token.startswith("0"):
        _fail("KV1300", "glyphs byte length has a leading-zero alias", line, 1)
    if len(size_token) > 6:
        _fail("KV1300", "glyphs byte length exceeds literal budget", line, 1)
    expected = int(size_token)
    if expected > MAX_GLYPHS_LITERAL_BYTES:
        _fail("KV1300", f"glyphs literal exceeds {MAX_GLYPHS_LITERAL_BYTES} bytes", line, 1)
    payload = " ".join(tokens[2:]) if len(tokens) > 2 else ""
    if payload != unicodedata.normalize("NFC", payload):
        _fail("KV1301", "glyphs payload must be Unicode NFC canonical", line, 1)
    actual = len(payload.encode("utf-8"))
    if actual != expected:
        _fail("KV1302", f"glyphs byte length says {expected} but payload is {actual} bytes", line, 1)
    return ValueTerm(None, (ValueAtom(literal=NativeValue(GLYPHS, payload)),))


def _term(tokens: list[str], *, line: int) -> ValueTerm:
    if not tokens:
        _fail("KV1005", "witness requires a value term", line, 1)
    if tokens[0] == "truth":
        if len(tokens) != 2 or tokens[1] not in {"yes", "no"}:
            _fail("KV1303", "truth literal is exactly: truth yes|no", line, 1)
        return ValueTerm(None, (ValueAtom(literal=NativeValue(TRUTH, tokens[1] == "yes")),))
    if tokens[0] == "glyphs":
        return _glyphs_term(tokens, line=line)
    if len(tokens) == 1:
        return ValueTerm(None, (_plain_atom(tokens[0], line=line),))
    if len(tokens) == 3 and tokens[0] in _BINARY_OPS:
        return ValueTerm(tokens[0], (_plain_atom(tokens[1], line=line), _plain_atom(tokens[2], line=line)))
    _fail(
        "KV1005",
        "term is an atom, truth yes|no, glyphs <utf8-bytes> <payload>, or a two-atom native operation",
        line,
        1,
    )
    raise AssertionError("unreachable")


def parse_native_value_graph(source: str) -> NativeValueGraph:
    lines = _canonical_lines(source)
    witnesses: list[ValueWitness] = []
    seen: set[str] = set()
    resolve_name: str | None = None
    resolve_location: SourceLocation | None = None
    for line_number, line in enumerate(lines, start=1):
        tokens = line.split(" ")
        head = tokens[0]
        # Legacy punctuation is forbidden outside glyph payload bytes.  This keeps
        # grammar shape distinct while allowing human text such as "hello, world"
        # inside an explicitly length-bound glyphs value.
        grammar_prefix = line
        if len(tokens) >= 3 and tokens[0] == "witness" and tokens[2] == "glyphs":
            grammar_prefix = " ".join(tokens[:4]) if len(tokens) >= 4 else line
        for symbol in _LEGACY_SYMBOLS:
            if symbol in grammar_prefix:
                _fail("KV1006", f"legacy punctuation {symbol!r} is not native value grammar", line_number, 1)
        if head == "witness":
            if len(tokens) < 3:
                _fail("KV1005", "witness requires identity and term", line_number, 1)
            name = _name(tokens[1], line=line_number)
            if name in seen:
                _fail("KV1101", f"duplicate witness identity {name!r}", line_number, 1)
            seen.add(name)
            witnesses.append(ValueWitness(name, _term(tokens[2:], line=line_number), SourceLocation(line_number, 1)))
            if len(witnesses) > MAX_VALUE_WITNESSES:
                _fail("KV1102", f"value graph exceeds {MAX_VALUE_WITNESSES} witnesses", line_number, 1)
            continue
        if head == "resolve":
            if len(tokens) != 2:
                _fail("KV1005", "resolve requires exactly one witness identity", line_number, 1)
            if resolve_name is not None:
                _fail("KV1103", "value graph must contain exactly one resolve", line_number, 1)
            resolve_name = _name(tokens[1], line=line_number)
            resolve_location = SourceLocation(line_number, 1)
            continue
        if head in _LEGACY_WORDS:
            _fail("KV1006", f"legacy grammar word {head!r} is rejected", line_number, 1)
        _fail("KV1005", f"unknown native value clause {head!r}", line_number, 1)
    if not witnesses:
        _fail("KV1104", "value graph must contain at least one witness")
    if resolve_name is None or resolve_location is None:
        _fail("KV1103", "value graph must contain exactly one resolve")
    graph = NativeValueGraph(tuple(witnesses), resolve_name, resolve_location)
    dependency_order_value_graph(graph)
    return graph


def _dependencies(witness: ValueWitness) -> tuple[str, ...]:
    return tuple(atom.witness for atom in witness.term.atoms if atom.witness is not None)


def dependency_order_value_graph(graph: NativeValueGraph) -> tuple[str, ...]:
    by_name = graph.by_name()
    if graph.resolve not in by_name:
        _fail("KV1105", f"resolve references unknown witness {graph.resolve!r}", graph.resolve_location.line, 1)
    state: dict[str, int] = {}
    ordered: list[str] = []
    reachable: set[str] = set()
    trail: list[str] = []
    stack: list[tuple[str, int]] = [(graph.resolve, 0)]
    while stack:
        name, index = stack[-1]
        witness = by_name[name]
        if state.get(name, 0) == 0:
            state[name] = 1
            reachable.add(name)
            trail.append(name)
        dependencies = _dependencies(witness)
        if index < len(dependencies):
            dependency = dependencies[index]
            stack[-1] = (name, index + 1)
            target = by_name.get(dependency)
            if target is None:
                _fail("KV1105", f"witness {name!r} references unknown witness {dependency!r}", witness.location.line, 1)
            mark = state.get(dependency, 0)
            if mark == 1:
                start = trail.index(dependency) if dependency in trail else 0
                _fail("KV1106", "value graph contains a cycle: " + " -> ".join((*trail[start:], dependency)), target.location.line, 1)
            if mark == 0:
                stack.append((dependency, 0))
            else:
                reachable.add(dependency)
            continue
        stack.pop()
        if trail and trail[-1] == name:
            trail.pop()
        state[name] = 2
        ordered.append(name)
    dormant = sorted(set(by_name) - reachable)
    if dormant:
        _fail("KV1107", "value graph contains dormant witnesses outside resolved reality: " + ", ".join(dormant), by_name[dormant[0]].location.line, 1)
    return tuple(ordered)


def evaluate_native_value_graph(graph: NativeValueGraph) -> dict[str, NativeValue]:
    by_name = graph.by_name()
    values: dict[str, NativeValue] = {}

    def atom_value(atom: ValueAtom) -> NativeValue:
        if atom.literal is not None:
            return atom.literal
        assert atom.witness is not None
        return values[atom.witness]

    for name in dependency_order_value_graph(graph):
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            value = atom_value(term.atoms[0])
        else:
            left = atom_value(term.atoms[0])
            right = atom_value(term.atoms[1])
            operation = term.operation
            if operation in _NUMERIC_OPS:
                if left.domain != WHOLE or right.domain != WHOLE:
                    _fail("KV1401", f"{operation} requires whole/whole and forbids coercion", witness.location.line, 1)
                a = int(left.value)
                b = int(right.value)
                if operation == "sum":
                    result = a + b
                elif operation == "difference":
                    result = a - b
                else:
                    result = a * b
                if not INT_MIN <= result <= INT_MAX:
                    _fail("KV1402", f"{operation} exceeds signed Int64 reality", witness.location.line, 1)
                value = NativeValue(WHOLE, result)
            elif operation == "same":
                if left.domain != right.domain:
                    _fail("KV1403", "same requires identical value domains and forbids cross-domain equality coercion", witness.location.line, 1)
                value = NativeValue(TRUTH, left.value == right.value)
            elif operation == "merge":
                if left.domain != GLYPHS or right.domain != GLYPHS:
                    _fail("KV1404", "merge requires glyphs/glyphs and forbids textual coercion", witness.location.line, 1)
                merged = str(left.value) + str(right.value)
                if len(merged.encode("utf-8")) > MAX_GLYPHS_RESULT_BYTES:
                    _fail("KV1405", "merged glyphs exceeds result byte budget", witness.location.line, 1)
                value = NativeValue(GLYPHS, merged)
            else:
                _fail("KV1005", f"unknown value operation {operation!r}", witness.location.line, 1)
        values[name] = value
    return values


def _lower_value(value: NativeValue, location: SourceLocation):
    return Literal(value.value, location)


def _type_ref(domain: str, location: SourceLocation) -> TypeRef:
    names = {WHOLE: "Int", TRUTH: "Bool", GLYPHS: "String"}
    try:
        return TypeRef((names[domain],), location)
    except KeyError:
        _fail("KV1500", f"unsupported backend value domain {domain!r}", location.line, 1)
    raise AssertionError("unreachable")


def lower_native_value_graph(graph: NativeValueGraph, values: dict[str, NativeValue]) -> Program:
    by_name = graph.by_name()
    statements = []
    operators = {"sum": "+", "difference": "-", "product": "*", "same": "==", "merge": "+"}
    for name in dependency_order_value_graph(graph):
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            atom = term.atoms[0]
            expression = _lower_value(atom.literal, witness.location) if atom.literal is not None else Identifier(atom.witness, witness.location)
        else:
            left, right = term.atoms
            left_expr = _lower_value(left.literal, witness.location) if left.literal is not None else Identifier(left.witness, witness.location)
            right_expr = _lower_value(right.literal, witness.location) if right.literal is not None else Identifier(right.witness, witness.location)
            expression = BinaryExpression(left_expr, operators[term.operation], right_expr, witness.location)
        statements.append(LetStatement(witness.name, False, expression, witness.location, _type_ref(values[name].domain, witness.location)))
    statements.append(ReturnStatement(Identifier(graph.resolve, graph.resolve_location), graph.resolve_location))
    resolved = values[graph.resolve]
    origin = GenericFunctionDeclaration(
        name="main",
        parameters=(),
        return_type=_type_ref(resolved.domain, SourceLocation(1, 1)),
        body=Block(tuple(statements)),
        location=SourceLocation(1, 1),
        is_pure=True,
        type_parameters=(),
        is_transition=False,
    )
    return Program((origin,))


def check_native_value_domains(source: str) -> NativeValueDomainCheck:
    graph = parse_native_value_graph(source)
    order = dependency_order_value_graph(graph)
    values = evaluate_native_value_graph(graph)
    lowered = lower_native_value_graph(graph, values)
    semantic = SemanticChecker(lowered).check()
    return NativeValueDomainCheck(graph, order, values, values[graph.resolve], lowered, semantic)
