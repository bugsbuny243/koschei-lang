import pytest

from koschei.quantum_reality_contract_v1 import (
    QuantumGateV1,
    QuantumRealityContractError,
    build_quantum_reality_contract_v1,
)


def test_quantum_contract_is_deterministic_and_committed():
    gates = (
        QuantumGateV1("H", (0,)),
        QuantumGateV1("CNOT", (0, 1)),
        QuantumGateV1("MEASURE", (0,)),
        QuantumGateV1("MEASURE", (1,)),
    )
    a = build_quantum_reality_contract_v1(qubits=2, gates=gates)
    b = build_quantum_reality_contract_v1(qubits=2, gates=gates)
    assert a.contract_digest == b.contract_digest
    assert len(a.contract_digest) == 32


def test_gate_order_changes_contract_identity():
    a = build_quantum_reality_contract_v1(
        qubits=1,
        gates=(QuantumGateV1("H", (0,)), QuantumGateV1("Z", (0,))),
    )
    b = build_quantum_reality_contract_v1(
        qubits=1,
        gates=(QuantumGateV1("Z", (0,)), QuantumGateV1("H", (0,))),
    )
    assert a.contract_digest != b.contract_digest


def test_invalid_topology_fails_closed():
    with pytest.raises(QuantumRealityContractError):
        build_quantum_reality_contract_v1(qubits=1, gates=(QuantumGateV1("CNOT", (0, 1)),))
    with pytest.raises(QuantumRealityContractError):
        build_quantum_reality_contract_v1(qubits=2, gates=(QuantumGateV1("CNOT", (0, 0)),))


def test_post_measurement_unitary_is_rejected_in_v1():
    with pytest.raises(QuantumRealityContractError):
        build_quantum_reality_contract_v1(
            qubits=1,
            gates=(QuantumGateV1("MEASURE", (0,)), QuantumGateV1("X", (0,))),
        )


def test_contract_has_no_execution_surface():
    contract = build_quantum_reality_contract_v1(
        qubits=1, gates=(QuantumGateV1("H", (0,)),)
    )
    assert not hasattr(contract, "execute")
    assert not hasattr(contract, "submit")
    assert not hasattr(contract, "backend")
