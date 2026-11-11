from dataclasses import replace
import hashlib

import pytest

from koschei.khar_failure_independence_v1 import (
    AxisFailureRootAttestation,
    KharFailureIndependenceError,
    seal_failure_independent_sathra,
)
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def sathra():
    return seal_sathra(
        AxisWitness(
            axis=axis,
            aevra_digest=d("aevra"),
            veyra_digest=d("veyra"),
            event_digest=d("event"),
            reality_digest=d("reality"),
            epoch=7,
            witness_digest=d("witness-" + axis),
        )
        for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )


def attestations(s):
    witnesses = dict(s.axis_witnesses)
    return tuple(
        AxisFailureRootAttestation(
            axis=axis,
            axis_witness_digest=witnesses[axis],
            failure_root_digest=d("root-" + axis),
            attestation_domain_digest=d("attestor-" + axis),
            evidence_digest=d("evidence-" + axis),
        )
        for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )


def test_six_distinct_roots_seal_failure_independent_sathra():
    s = sathra()
    proof = seal_failure_independent_sathra(s, attestations(s))
    proof.assert_sealed(s)
    assert proof.sathra_digest == s.digest
    assert len(proof.roots) == 6


def test_one_hidden_root_cannot_back_two_axes():
    s = sathra()
    items = list(attestations(s))
    items[1] = replace(items[1], failure_root_digest=items[0].failure_root_digest)
    with pytest.raises(KharFailureIndependenceError, match="six distinct failure roots"):
        seal_failure_independent_sathra(s, items)


def test_one_attestation_domain_cannot_certify_two_axes():
    s = sathra()
    items = list(attestations(s))
    items[3] = replace(
        items[3], attestation_domain_digest=items[2].attestation_domain_digest
    )
    with pytest.raises(KharFailureIndependenceError, match="six distinct attestation domains"):
        seal_failure_independent_sathra(s, items)


def test_failure_root_cannot_be_another_axis_attestation_domain():
    s = sathra()
    items = list(attestations(s))
    items[5] = replace(
        items[5], attestation_domain_digest=items[0].failure_root_digest
    )
    with pytest.raises(KharFailureIndependenceError, match="another axis attestation domain"):
        seal_failure_independent_sathra(s, items)


def test_attestation_must_bind_exact_sathra_axis_witness():
    s = sathra()
    items = list(attestations(s))
    items[0] = replace(items[0], axis_witness_digest=d("foreign-witness"))
    with pytest.raises(KharFailureIndependenceError, match="does not match Sathra axis"):
        seal_failure_independent_sathra(s, items)


def test_failure_root_cannot_self_attest():
    with pytest.raises(KharFailureIndependenceError, match="cannot self-attest"):
        AxisFailureRootAttestation(
            axis="khor",
            axis_witness_digest=d("witness"),
            failure_root_digest=d("same"),
            attestation_domain_digest=d("same"),
            evidence_digest=d("evidence"),
        )


def test_tampered_failure_independence_proof_fails_closed():
    s = sathra()
    proof = seal_failure_independent_sathra(s, attestations(s))
    forged = replace(proof, digest=d("forged"))
    with pytest.raises(KharFailureIndependenceError, match="seal mismatch"):
        forged.assert_sealed(s)
