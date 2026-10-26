"""Koschei-native semantic kernel v1.

This is deliberately *not* a keyword-renamed function language. A source object
is one closed immutable value graph:

    witness base 40
    witness fee 2
    witness total sum base fee
    resolve total

`witness` nodes are equations in a dependency graph, not sequential variable
statements. Source order has no execution meaning: forward references are valid,
and lowering uses dependency order. `resolve` selects the single observable value
of the closed graph; it is not an early-control-flow return statement.

The v1 kernel is intentionally small and pure. It admits only signed Int64 values
and the general mathematical operations sum/difference/product. There is no
function declaration, mutable binding, branch, loop, import, ambient authority,
semantic filename, brace block or infix operator in the native surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

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


MAX_NATIVE_SOURCE_BYTES = 1 << 20
MAX_WITNESSES = 4096
MAX_NAME_BYTES = 64
_NATIVE_NAME = re.compile(r"^[a-z][a-z0-9]{0,63}$")
_NATIVE_WORDS = frozenset({"witness", "resolve", "sum", "difference", "product"})
_OPERATIONS = frozenset({"sum", "difference", "product"})
_LEGACY_DEBT_WORDS = frozenset(
    {
        "pure", "stateful", "fn", "let", "mut", "or", "return", "if", "else",
        "while", "for", "in", "break", "continue", "struct", "enum", "match",
        "import", "true", "false",
    }
)
_LEGACY_DEBT_SYMBOLS = frozenset(
    {
        "(", ")", "{", "}", "[", "]", ",", ":", ".", "=", "+", "-", "*",
        "/", "%", ";", "!", "<", ">", "->", "=>", "==", "!=", "<=", ">=",
        "&&", "||",
    }
)


class NativeKernelError(ValueError):
    def __init__(self, code: str, message: str, line: int = 1, column: int = 1) -> None:
        self.code = code
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"{code} [line {line}, column {column}]: {message}")


@dataclass(frozen=True, slots=True)
class NativeAtom:
    literal: int | None = None
    witness: str | None = None

    def __post_init__(self) -> None:
        if (self.literal is None) == (self.witness is None):
            raise ValueError("native atom must contain exactly one literal or witness reference")


@dataclass(frozen=True, slots=True)
class NativeTerm:
    operation: str | None
    atoms: tuple[NativeAtom, ...]


@dataclass(frozen=True, slots=True)
class NativeWitness:
    name: str
    term: NativeTerm
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class NativeKernel:
    witnesses: tuple[NativeWitness, ...]
    resolve: str
    resolve_location: SourceLocation

    def by_name(self) -> dict[str, NativeWitness]:
        return {item.name: item for item in self.witnesses}


@dataclass(frozen=True, slots=True)
class NativeKernelCheck:
    kernel: NativeKernel
    dependency_order: tuple[str, ...]
    value: int
    lowered: Program
    semantic: SemanticReport


def native_surface_words_v1() -> frozenset[str]:
    return _NATIVE_WORDS


def _fail(code: str, message: str, line: int = 1, column: int = 1) -> None:
    raise NativeKernelError(code, message, line, column)


def _canonical_source(source: object) -> tuple[str, ...]:
    if not isinstance(source, str):
        _fail("KN1000", "native source must be text")
    if "\x00" in source:
        _fail("KN1000", "NUL is forbidden in native source")
    try:
        payload = source.encode("ascii")
    except UnicodeEncodeError as error:
        _fail(
            "KN1001",
            "native kernel v1 admits ASCII only; Unicode confusables and normalization aliases fail closed",
            source.count("\n", 0, error.start) + 1,
            1,
        )
    if len(payload) > MAX_NATIVE_SOURCE_BYTES:
        _fail("KN1002", f"native source exceeds {MAX_NATIVE_SOURCE_BYTES} bytes")
    if "\r" in source or "\t" in source:
        _fail("KN1003", "native source requires LF newlines and forbids tabs")
    if not source.endswith("\n") or source.endswith("\n\n"):
        _fail("KN1003", "native source must end in exactly one LF")

    lines = tuple(source[:-1].split("\n"))
    if not lines or any(not line for line in lines):
        _fail("KN1003", "blank clauses are not canonical in native kernel v1")
    for number, line in enumerate(lines, start=1):
        if line != line.strip() or "  " in line or " ".join(line.split(" ")) != line:
            _fail(
                "KN1003",
                "each native clause uses one ASCII space between tokens and no indentation/trailing space",
                number,
                1,
            )
    return lines


def _name(token: str, *, line: int) -> str:
    if token in _NATIVE_WORDS or token in _LEGACY_DEBT_WORDS:
        _fail("KN1004", f"{token!r} is reserved and cannot be a witness identity", line, 1)
    if _NATIVE_NAME.fullmatch(token) is None or len(token.encode("ascii")) > MAX_NAME_BYTES:
        _fail(
            "KN1004",
            "witness identity must be 1..64 bytes of lowercase ASCII letters/digits and start with a letter",
            line,
            1,
        )
    return token


def _atom(token: str, *, line: int) -> NativeAtom:
    if token.isdigit():
        if len(token) > 1 and token.startswith("0"):
            _fail(
                "KN1200",
                "Int literal is non-canonical; leading-zero decimal aliases are forbidden",
                line,
                1,
            )
        if len(token) > 19 or (len(token) == 19 and token > str(INT_MAX)):
            _fail("KN1201", "Int literal exceeds signed Int64 range", line, 1)
        return NativeAtom(literal=int(token))
    return NativeAtom(witness=_name(token, line=line))


def _term(tokens: list[str], *, line: int) -> NativeTerm:
    if len(tokens) == 1:
        return NativeTerm(None, (_atom(tokens[0], line=line),))
    if len(tokens) == 3 and tokens[0] in _OPERATIONS:
        return NativeTerm(
            tokens[0],
            (_atom(tokens[1], line=line), _atom(tokens[2], line=line)),
        )
    _fail(
        "KN1005",
        "witness term is either one atom or exactly: sum|difference|product <atom> <atom>",
        line,
        1,
    )
    raise AssertionError("unreachable")


def parse_native_kernel(source: str) -> NativeKernel:
    """Parse the native closed-graph surface without consulting the legacy lexer/parser."""

    lines = _canonical_source(source)
    witnesses: list[NativeWitness] = []
    seen: set[str] = set()
    resolve_name: str | None = None
    resolve_location: SourceLocation | None = None

    for line_number, line in enumerate(lines, start=1):
        for symbol in _LEGACY_DEBT_SYMBOLS:
            if symbol in line:
                _fail(
                    "KN1006",
                    f"legacy punctuation {symbol!r} is not part of native kernel v1",
                    line_number,
                    line.index(symbol) + 1,
                )

        tokens = line.split(" ")
        head = tokens[0]
        if head == "witness":
            if len(tokens) < 3:
                _fail("KN1005", "witness requires an identity and term", line_number, 1)
            name = _name(tokens[1], line=line_number)
            if name in seen:
                _fail("KN1101", f"duplicate witness identity {name!r}", line_number, 1)
            seen.add(name)
            witnesses.append(
                NativeWitness(
                    name,
                    _term(tokens[2:], line=line_number),
                    SourceLocation(line_number, 1),
                )
            )
            if len(witnesses) > MAX_WITNESSES:
                _fail("KN1102", f"native graph exceeds {MAX_WITNESSES} witnesses", line_number, 1)
            continue

        if head == "resolve":
            if len(tokens) != 2:
                _fail("KN1005", "resolve requires exactly one witness identity", line_number, 1)
            if resolve_name is not None:
                _fail("KN1103", "native graph must contain exactly one resolve clause", line_number, 1)
            resolve_name = _name(tokens[1], line=line_number)
            resolve_location = SourceLocation(line_number, 1)
            continue

        if head in _LEGACY_DEBT_WORDS:
            _fail(
                "KN1006",
                f"legacy grammar word {head!r} is rejected by the native frontend",
                line_number,
                1,
            )
        _fail("KN1005", f"unknown native clause {head!r}", line_number, 1)

    if not witnesses:
        _fail("KN1104", "native graph must contain at least one witness")
    if resolve_name is None or resolve_location is None:
        _fail("KN1103", "native graph must contain exactly one resolve clause")

    kernel = NativeKernel(tuple(witnesses), resolve_name, resolve_location)
    dependency_order(kernel)
    return kernel


def _dependencies(witness: NativeWitness) -> tuple[str, ...]:
    return tuple(atom.witness for atom in witness.term.atoms if atom.witness is not None)


def dependency_order(kernel: NativeKernel) -> tuple[str, ...]:
    """Return canonical dependency order without host recursion.

    V1 admits 4096 witnesses. A recursive DFS would make Python's call-stack
    limit an accidental language limit, so graph admission uses an explicit stack.
    """

    by_name = kernel.by_name()
    if len(by_name) != len(kernel.witnesses):
        _fail("KN1101", "native kernel contains duplicate witness identities")
    if kernel.resolve not in by_name:
        _fail(
            "KN1105",
            f"resolve references unknown witness {kernel.resolve!r}",
            kernel.resolve_location.line,
            kernel.resolve_location.column,
        )

    state: dict[str, int] = {}
    ordered: list[str] = []
    reachable: set[str] = set()
    trail: list[str] = []
    stack: list[tuple[str, int]] = [(kernel.resolve, 0)]

    while stack:
        name, next_dependency = stack[-1]
        witness = by_name[name]
        if state.get(name, 0) == 0:
            state[name] = 1
            reachable.add(name)
            trail.append(name)

        dependencies = _dependencies(witness)
        if next_dependency < len(dependencies):
            dependency = dependencies[next_dependency]
            stack[-1] = (name, next_dependency + 1)
            target = by_name.get(dependency)
            if target is None:
                _fail(
                    "KN1105",
                    f"witness {name!r} references unknown witness {dependency!r}",
                    witness.location.line,
                    witness.location.column,
                )
            mark = state.get(dependency, 0)
            if mark == 1:
                try:
                    cycle_start = trail.index(dependency)
                except ValueError:
                    cycle_start = 0
                cycle = " -> ".join((*trail[cycle_start:], dependency))
                _fail(
                    "KN1106",
                    f"native witness graph contains a cycle: {cycle}",
                    target.location.line,
                    1,
                )
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
        first = by_name[dormant[0]]
        _fail(
            "KN1107",
            "native object contains dormant witnesses outside the resolved reality: "
            + ", ".join(dormant),
            first.location.line,
            1,
        )
    return tuple(ordered)


def _checked_int(value: int, *, operation: str, location: SourceLocation) -> int:
    if not INT_MIN <= value <= INT_MAX:
        _fail(
            "KN1202",
            f"{operation} exceeds signed Int64 reality",
            location.line,
            location.column,
        )
    return value


def evaluate_native_kernel(kernel: NativeKernel) -> int:
    by_name = kernel.by_name()
    values: dict[str, int] = {}

    def atom_value(atom: NativeAtom) -> int:
        if atom.literal is not None:
            return atom.literal
        assert atom.witness is not None
        return values[atom.witness]

    for name in dependency_order(kernel):
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            value = atom_value(term.atoms[0])
        else:
            left = atom_value(term.atoms[0])
            right = atom_value(term.atoms[1])
            if term.operation == "sum":
                value = left + right
            elif term.operation == "difference":
                value = left - right
            elif term.operation == "product":
                value = left * right
            else:
                _fail("KN1005", f"unknown native operation {term.operation!r}", witness.location.line, 1)
            value = _checked_int(value, operation=term.operation, location=witness.location)
        values[name] = value
    return values[kernel.resolve]


def _lower_atom(atom: NativeAtom, location: SourceLocation):
    if atom.literal is not None:
        return Literal(atom.literal, location)
    assert atom.witness is not None
    return Identifier(atom.witness, location)


def lower_native_kernel(kernel: NativeKernel) -> Program:
    """Lower native graph semantics into the existing typed backend AST.

    The sequential legacy nodes produced here are an internal compatibility IR,
    not the source-language semantics. Topological order is computed from graph
    dependencies and therefore does not inherit source-line execution order.
    """

    by_name = kernel.by_name()
    statements = []
    operators = {"sum": "+", "difference": "-", "product": "*"}
    for name in dependency_order(kernel):
        witness = by_name[name]
        term = witness.term
        if term.operation is None:
            expression = _lower_atom(term.atoms[0], witness.location)
        else:
            expression = BinaryExpression(
                _lower_atom(term.atoms[0], witness.location),
                operators[term.operation],
                _lower_atom(term.atoms[1], witness.location),
                witness.location,
            )
        statements.append(
            LetStatement(
                witness.name,
                False,
                expression,
                witness.location,
                TypeRef(("Int",), witness.location),
            )
        )
    statements.append(
        ReturnStatement(
            Identifier(kernel.resolve, kernel.resolve_location),
            kernel.resolve_location,
        )
    )
    # The backend's canonical function node carries the complete current AST ABI
    # (including empty generic/transition axes). Native source still has no
    # function declaration; this node exists only below the frontend boundary.
    origin = GenericFunctionDeclaration(
        name="main",
        parameters=(),
        return_type=TypeRef(("Int",), SourceLocation(1, 1)),
        body=Block(tuple(statements)),
        location=SourceLocation(1, 1),
        is_pure=True,
        type_parameters=(),
        is_transition=False,
    )
    return Program((origin,))


def check_native_kernel(source: str) -> NativeKernelCheck:
    kernel = parse_native_kernel(source)
    lowered = lower_native_kernel(kernel)
    semantic = SemanticChecker(lowered).check()
    return NativeKernelCheck(
        kernel=kernel,
        dependency_order=dependency_order(kernel),
        value=evaluate_native_kernel(kernel),
        lowered=lowered,
        semantic=semantic,
    )