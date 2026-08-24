import hashlib
from types import SimpleNamespace

import pytest

import koschei.khar_witnessed_galaxy_execution_v1 as gate
from koschei.khar_constitution_v1 import birth_canonical_veyra
from koschei.khar_implementation_root_v1 import (
    build_khar_implementation_measurement,
    seal_khar_implementation_witness,
    verify_khar_implementation_root,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def make_root(*, epoch: int = 9):
    veyra = birth_canonical_veyra(
        profile_digest=d("profile"),
        genesis_digest=d("genesis"),
        instance_digest=d("customer-a"),
        birth_epoch=1,
    )
    measured = build_khar_implementation_measurement(
        veyra_digest=veyra.digest,
        native_mir_fingerprint=d("native-mir"),
        epoch=epoch,
        compiler_sha256=d("compiler"),
        runtime_sha256=d("runtime"),
        native_build_manifest_digest=d("build"),
        release_proof_digest=d("release"),
        maturity_attestation_digest=d("maturity"),
        ci_head_sha="b" * 40,
    )
    key_a = b"A" * 32
    key_b = b"B" * 32
    witness_a = seal_khar_implementation_witness(
        measured,
        witness_id="host",
        failure_root="host-root",
        key=key_a,
    )
    witness_b = seal_khar_implementation_witness(
        measured,
        witness_id="release",
        failure_root="release-root",
        key=key_b,
    )
    root = verify_khar_implementation_root(
        measured,
        (witness_a, witness_b),
        witness_keys={"host": key_a, "release": key_b},
    )
    return veyra, root


def call_gate(monkeypatch, *, request_epoch: int, root_epoch: int = 9):
    veyra, root = make_root(epoch=root_epoch)
    observed = {}

    def delegate(**kwargs):
        observed.update(kwargs)
        return ("decision", "effect-result", "claim")

    monkeypatch.setattr(gate, "enforce_galaxy_critical_effect", delegate)
    result = gate.enforce_witnessed_galaxy_critical_effect(
        implementation_root=root,
        black_hole=object(),
        matrix_horizon=object(),
        coordinator=object(),
        mir=SimpleNamespace(fingerprint=d("native-mir")),
        veyra=veyra,
        aevra=object(),
        matrix=object(),
        hara=object(),
        matrix_admission=object(),
        request=SimpleNamespace(epoch=request_epoch),
        proof=object(),
        request_bound_proof=object(),
        sathra=object(),
        sathra_binding=object(),
        failure_independence=object(),
        effect=lambda request: request,
    )
    return result, observed


def test_witnessed_root_must_pass_before_base_galaxy_gate(monkeypatch):
    result, observed = call_gate(monkeypatch, request_epoch=9)

    assert result == ("decision", "effect-result", "claim")
    assert observed["veyra"].digest
    assert observed["mir"].fingerprint == d("native-mir")
    assert observed["request"].epoch == 9


def test_stale_witnessed_root_cannot_reach_base_galaxy_gate(monkeypatch):
    called = False

    def delegate(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("base Galaxy gate must not be reached")

    monkeypatch.setattr(gate, "enforce_galaxy_critical_effect", delegate)
    veyra, root = make_root(epoch=8)

    with pytest.raises(
        gate.KharWitnessedGalaxyExecutionError,
        match="different epoch",
    ):
        gate.enforce_witnessed_galaxy_critical_effect(
            implementation_root=root,
            black_hole=object(),
            matrix_horizon=object(),
            coordinator=object(),
            mir=SimpleNamespace(fingerprint=d("native-mir")),
            veyra=veyra,
            aevra=object(),
            matrix=object(),
            hara=object(),
            matrix_admission=object(),
            request=SimpleNamespace(epoch=9),
            proof=object(),
            request_bound_proof=object(),
            sathra=object(),
            sathra_binding=object(),
            failure_independence=object(),
            effect=lambda request: request,
        )
    assert called is False
