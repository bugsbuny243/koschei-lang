"""Koschei-native Algebra Reality v1.

This slice makes exact mathematics a first-class Reality instead of smuggling
numeric behavior through host language operators.  V1 uses a prime field F_p:
all values are canonical residues and every admitted operation is defined by the
field itself.

Surface:
    field 2147483647
    witness a scalar 7
    witness b scalar 9
    witness c add a b
    witness d mul c b
    witness e inv b
    resolve d

This is not Python/Rust arithmetic syntax.  The field modulus is part of the
Reality identity and arithmetic has no overflow, float, coercion, NaN or host
integer ambiguity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

_CONTEXT = b"koschei.native-algebra-reality/v1\x00"
MAX_FIELD = (1 << 63) - 25
MAX_WITNESSES = 4096


class NativeAlgebraRealityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlgebraWitnessV1:
    name: str
    op: str
    args: tuple[str, ...]
    literal: int | None


@dataclass(frozen=True, slots=True)
class AlgebraRealityV1:
    modulus: int
    witnesses: tuple[AlgebraWitnessV1, ...]
    resolve: str
    values: dict[str, int]
    value: int
    reality_digest: bytes


def _fail(message: str) -> None:
    raise NativeAlgebraRealityError(message)


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True


def _name(token: str) -> str:
    if not token or not token.isascii() or not token.replace("_", "a").isalnum() or token[0].isdigit():
        _fail("non-canonical algebra witness identity")
    return token


def _u(token: str, label: str) -> int:
    if not token.isascii() or not token.isdigit() or (len(token) > 1 and token[0] == "0"):
        _fail(f"{label} must be canonical unsigned decimal")
    return int(token)


def evaluate_native_algebra_reality_v1(source: str) -> AlgebraRealityV1:
    if not isinstance(source, str):
        _fail("algebra source must be text")
    lines = tuple(line.strip() for line in source.splitlines() if line.strip())
    if not lines or len(lines) < 3:
        _fail("algebra reality is incomplete")
    head = lines[0].split()
    if len(head) != 2 or head[0] != "field":
        _fail("first algebra clause must be: field <prime>")
    modulus = _u(head[1], "field modulus")
    if modulus > MAX_FIELD or not _is_prime(modulus):
        _fail("field modulus must be an admitted prime")

    witnesses: list[AlgebraWitnessV1] = []
    seen: set[str] = set()
    resolve: str | None = None
    for line in lines[1:]:
        tokens = line.split()
        if tokens[0] == "resolve":
            if len(tokens) != 2 or resolve is not None:
                _fail("algebra reality requires exactly one resolve")
            resolve = _name(tokens[1])
            continue
        if tokens[0] != "witness" or len(tokens) < 4:
            _fail("unknown algebra clause")
        name = _name(tokens[1])
        if name in seen:
            _fail("duplicate algebra witness")
        seen.add(name)
        op = tokens[2]
        if op == "scalar":
            if len(tokens) != 4:
                _fail("scalar form is: witness <name> scalar <value>")
            value = _u(tokens[3], "scalar")
            if value >= modulus:
                _fail("scalar must be canonical residue below field modulus")
            witness = AlgebraWitnessV1(name, op, (), value)
        elif op in {"add", "sub", "mul"}:
            if len(tokens) != 5:
                _fail(f"{op} requires exactly two witnesses")
            witness = AlgebraWitnessV1(name, op, (_name(tokens[3]), _name(tokens[4])), None)
        elif op == "inv":
            if len(tokens) != 4:
                _fail("inv requires exactly one witness")
            witness = AlgebraWitnessV1(name, op, (_name(tokens[3]),), None)
        else:
            _fail("unsupported algebra operation")
        witnesses.append(witness)
        if len(witnesses) > MAX_WITNESSES:
            _fail("algebra witness budget exceeded")

    if resolve is None or resolve not in seen:
        _fail("resolve references unknown algebra witness")

    by_name = {w.name: w for w in witnesses}
    values: dict[str, int] = {}
    pending = set(by_name)
    while pending:
        progressed = False
        for name in tuple(pending):
            w = by_name[name]
            if w.op == "scalar":
                assert w.literal is not None
                values[name] = w.literal
            elif any(arg not in values for arg in w.args):
                continue
            elif w.op == "add":
                values[name] = (values[w.args[0]] + values[w.args[1]]) % modulus
            elif w.op == "sub":
                values[name] = (values[w.args[0]] - values[w.args[1]]) % modulus
            elif w.op == "mul":
                values[name] = (values[w.args[0]] * values[w.args[1]]) % modulus
            elif w.op == "inv":
                value = values[w.args[0]]
                if value == 0:
                    _fail("zero has no multiplicative inverse")
                values[name] = pow(value, modulus - 2, modulus)
            pending.remove(name)
            progressed = True
        if not progressed:
            _fail("algebra reality contains unknown dependency or cycle")

    canonical = [b"field", str(modulus).encode("ascii")]
    for name in sorted(values):
        canonical.extend((name.encode("ascii"), str(values[name]).encode("ascii")))
    canonical.extend((b"resolve", resolve.encode("ascii")))
    digest = hashlib.sha3_256(_CONTEXT + b"\x00".join(canonical)).digest()
    return AlgebraRealityV1(modulus, tuple(witnesses), resolve, values, values[resolve], digest)
