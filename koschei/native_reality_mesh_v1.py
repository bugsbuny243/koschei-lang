"""Koschei-native Reality Mesh v1.

A mesh is not a List/Map/array rename. It is a bounded, immutable, order-free
collection reality whose identity is derived from the canonical values it admits.
Source order is non-semantic: the same admitted members yield the same mesh digest.
Duplicates are rejected rather than silently preserved.

Surface:
    witness a 7
    witness b 9
    witness group mesh 2 a b
    witness size span group
    witness hasb contains group b
    resolve size

This module is deliberately frontend-only and does not extend legacy collection
syntax. It composes over Native Value Domains v1.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from . import native_value_domains_v1 as base

MESH = "mesh"
SPAN = "span"
CONTAINS = "contains"
MAX_MESH_MEMBERS = 1024

class NativeRealityMeshError(base.NativeValueDomainError):
    pass

@dataclass(frozen=True, slots=True)
class MeshValue:
    domain: str
    members: tuple[base.NativeValue, ...]
    digest: bytes

@dataclass(frozen=True, slots=True)
class MeshWitness:
    name: str
    op: str | None
    args: tuple[str, ...]
    literal: base.NativeValue | None
    line: int

@dataclass(frozen=True, slots=True)
class MeshGraph:
    witnesses: tuple[MeshWitness, ...]
    resolve: str


def _fail(code: str, message: str, line: int = 1) -> None:
    raise NativeRealityMeshError(code, message, line, 1)


def _canonical_value_bytes(value: base.NativeValue) -> bytes:
    if value.domain == base.WHOLE:
        return b"whole\x00" + str(int(value.value)).encode("ascii")
    if value.domain == base.TRUTH:
        return b"truth\x00" + (b"yes" if bool(value.value) else b"no")
    if value.domain == base.GLYPHS:
        return b"glyphs\x00" + str(value.value).encode("utf-8")
    _fail("KM1400", "mesh cannot admit unknown value domain")
    raise AssertionError


def _mesh(values: Iterable[base.NativeValue], line: int) -> MeshValue:
    items = tuple(values)
    if not 1 <= len(items) <= MAX_MESH_MEMBERS:
        _fail("KM1401", f"mesh cardinality must be 1..{MAX_MESH_MEMBERS}", line)
    domains = {v.domain for v in items}
    if len(domains) != 1:
        _fail("KM1402", "mesh members must share one value domain", line)
    encoded = [_canonical_value_bytes(v) for v in items]
    if len(set(encoded)) != len(encoded):
        _fail("KM1403", "mesh rejects duplicate admitted values", line)
    ordered = sorted(zip(encoded, items), key=lambda pair: pair[0])
    canonical = tuple(item for _, item in ordered)
    payload = b"\x00".join(encoded for encoded, _ in ordered)
    digest = hashlib.sha3_256(b"koschei.reality-mesh/v1\x00" + payload).digest()
    return MeshValue(next(iter(domains)), canonical, digest)


def parse_native_reality_mesh_v1(source: str) -> MeshGraph:
    lines = base._canonical_lines(source)
    witnesses: list[MeshWitness] = []
    seen: set[str] = set()
    resolve: str | None = None
    for number, line in enumerate(lines, 1):
        tokens = line.split(" ")
        if tokens[0] == "resolve":
            if len(tokens) != 2 or resolve is not None:
                _fail("KM1100", "mesh reality requires exactly one resolve", number)
            resolve = base._name(tokens[1], line=number)
            continue
        if tokens[0] != "witness" or len(tokens) < 3:
            _fail("KM1000", "unknown native mesh clause", number)
        name = base._name(tokens[1], line=number)
        if name in seen:
            _fail("KM1101", f"duplicate witness identity {name!r}", number)
        seen.add(name)
        body = tokens[2:]
        if body[0] == MESH:
            if len(body) < 3 or not body[1].isdigit():
                _fail("KM1200", "mesh form is: mesh <count> <witness...>", number)
            count = int(body[1])
            args = tuple(body[2:])
            if count != len(args):
                _fail("KM1201", "mesh declared count does not match member count", number)
            witnesses.append(MeshWitness(name, MESH, args, None, number))
        elif body[0] == SPAN:
            if len(body) != 2:
                _fail("KM1202", "span form is: span <mesh-witness>", number)
            witnesses.append(MeshWitness(name, SPAN, (body[1],), None, number))
        elif body[0] == CONTAINS:
            if len(body) != 3:
                _fail("KM1203", "contains form is: contains <mesh-witness> <value-witness>", number)
            witnesses.append(MeshWitness(name, CONTAINS, (body[1], body[2]), None, number))
        else:
            try:
                term = base._term(body, line=number)
            except base.NativeValueDomainError as error:
                raise NativeRealityMeshError(error.code, error.message, error.line, error.column) from error
            if term.operation is not None or term.atoms[0].literal is None:
                _fail("KM1204", "mesh v1 ordinary witnesses must be canonical literals", number)
            witnesses.append(MeshWitness(name, None, (), term.atoms[0].literal, number))
    if resolve is None:
        _fail("KM1100", "mesh reality requires exactly one resolve")
    if resolve not in seen:
        _fail("KM1102", "resolve references unknown witness")
    return MeshGraph(tuple(witnesses), resolve)


def evaluate_native_reality_mesh_v1(source: str):
    graph = parse_native_reality_mesh_v1(source)
    values: dict[str, base.NativeValue | MeshValue] = {}
    pending = {w.name: w for w in graph.witnesses}
    while pending:
        progressed = False
        for name, witness in tuple(pending.items()):
            if witness.op is None:
                assert witness.literal is not None
                values[name] = witness.literal
            elif any(arg not in values for arg in witness.args):
                continue
            elif witness.op == MESH:
                members = [values[arg] for arg in witness.args]
                if any(isinstance(v, MeshValue) for v in members):
                    _fail("KM1404", "mesh-of-mesh is not admitted in v1", witness.line)
                values[name] = _mesh(members, witness.line)  # type: ignore[arg-type]
            elif witness.op == SPAN:
                target = values[witness.args[0]]
                if not isinstance(target, MeshValue):
                    _fail("KM1405", "span requires a mesh reality", witness.line)
                values[name] = base.NativeValue(base.WHOLE, len(target.members))
            elif witness.op == CONTAINS:
                target = values[witness.args[0]]
                needle = values[witness.args[1]]
                if not isinstance(target, MeshValue) or isinstance(needle, MeshValue):
                    _fail("KM1406", "contains requires mesh and scalar value", witness.line)
                if needle.domain != target.domain:
                    _fail("KM1407", "contains forbids cross-domain comparison", witness.line)
                key = _canonical_value_bytes(needle)
                values[name] = base.NativeValue(base.TRUTH, any(_canonical_value_bytes(v) == key for v in target.members))
            del pending[name]
            progressed = True
        if not progressed:
            _fail("KM1103", "mesh reality contains unknown dependency or cycle")
    return values[graph.resolve]
