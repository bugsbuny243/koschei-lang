"""Koschei Quantum Reality Contract v1.

This module defines a canonical quantum job descriptor for future real quantum
backends. It does NOT claim to execute on quantum hardware. The contract keeps
quantum state preparation, unitary evolution and measurement explicit and binds
them to a digest that can later be admitted by a separately-authorized backend.

Supported v1 operations are deliberately small: H, X, Z, CNOT and MEASURE.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal, Sequence

GateName = Literal["H", "X", "Z", "CNOT", "MEASURE"]
_ALLOWED = frozenset({"H", "X", "Z", "CNOT", "MEASURE"})
_CONTEXT = b"koschei.quantum-reality-contract/v1\x00"
MAX_QUBITS_V1 = 64
MAX_GATES_V1 = 4096


class QuantumRealityContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QuantumGateV1:
    gate: GateName
    qubits: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class QuantumRealityContractV1:
    qubits: int
    gates: tuple[QuantumGateV1, ...]
    contract_digest: bytes


def _fail(message: str) -> None:
    raise QuantumRealityContractError(message)


def build_quantum_reality_contract_v1(*, qubits: int,
    gates: Sequence[QuantumGateV1]) -> QuantumRealityContractV1:
    if not isinstance(qubits, int) or isinstance(qubits, bool) or not 1 <= qubits <= MAX_QUBITS_V1:
        _fail(f"qubits must be in 1..{MAX_QUBITS_V1}")
    if not isinstance(gates, Sequence) or isinstance(gates, (str, bytes, bytearray)):
        _fail("gates must be a canonical sequence")
    if not gates or len(gates) > MAX_GATES_V1:
        _fail(f"gate count must be in 1..{MAX_GATES_V1}")

    canonical: list[bytes] = [qubits.to_bytes(2, "big")]
    measured: set[int] = set()
    normalized: list[QuantumGateV1] = []
    for item in gates:
        if not isinstance(item, QuantumGateV1) or item.gate not in _ALLOWED:
            _fail("canonical QuantumGateV1 required")
        required = 2 if item.gate == "CNOT" else 1
        if len(item.qubits) != required:
            _fail(f"{item.gate} requires exactly {required} qubit(s)")
        if len(set(item.qubits)) != len(item.qubits):
            _fail("quantum gate cannot alias its qubits")
        if any(not isinstance(q, int) or isinstance(q, bool) or q < 0 or q >= qubits for q in item.qubits):
            _fail("quantum gate references out-of-range qubit")
        if any(q in measured for q in item.qubits) and item.gate != "MEASURE":
            _fail("v1 forbids unitary evolution after measurement of the same qubit")
        if item.gate == "MEASURE":
            q = item.qubits[0]
            if q in measured:
                _fail("duplicate measurement is not canonical")
            measured.add(q)
        normalized.append(item)
        canonical.append(item.gate.encode("ascii") + b":" + b",".join(str(q).encode("ascii") for q in item.qubits))

    digest = hashlib.sha3_256(_CONTEXT + b"\x00".join(canonical)).digest()
    return QuantumRealityContractV1(qubits, tuple(normalized), digest)
