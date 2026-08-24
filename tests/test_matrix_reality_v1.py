from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.matrix_reality_v1 import (
    MatrixRealityError,
    admit_matrix_hara,
    birth_hara,
    birth_matrix,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.parser import parse


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def mir(subject="withdrawal"):
    return lower_native_sigils(parse(f"ka treasury; vor {subject}; shi evidence;"))


def veyra(instance="bank-a"):
    return birth_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
        instance_digest=d(instance),
        birth_epoch=7,
    )


def aevra(v, m, subject="withdrawal", evidence="birth"):
    return birth_aevra(
        v,
        m,
        sigil="vor",
        subject=subject,
        birth_evidence_digest=d(evidence),
        birth_epoch=7,
    )


def test_two_aevras_can_share_matrix_without_sharing_hara():
    v = veyra()
    m1 = mir("withdrawal")
    m2 = mir("signing")
    a1 = aevra(v, m1, "withdrawal", "birth-a")
    a2 = aevra(v, m2, "signing", "birth-b")
    matrix = birth_matrix(
        v,
        instance_digest=d("matrix-1"),
        reality_commitment_digest=d("reality-1"),
        birth_epoch=7,
    )
    h1 = birth_hara(matrix, v, a1, m1, horizon_commitment_digest=d("hara-a"), epoch=7)
    h2 = birth_hara(matrix, v, a2, m2, horizon_commitment_digest=d("hara-b"), epoch=7)
    assert h1.matrix_digest == h2.matrix_digest
    assert h1.aevra_digest != h2.aevra_digest
    assert h1.digest != h2.digest


def test_hara_cannot_move_to_another_aevra_or_matrix():
    v = veyra()
    m = mir()
    a = aevra(v, m)
    matrix_a = birth_matrix(v, instance_digest=d("a"), reality_commitment_digest=d("ra"), birth_epoch=7)
    matrix_b = birth_matrix(v, instance_digest=d("b"), reality_commitment_digest=d("rb"), birth_epoch=7)
    hara = birth_hara(matrix_a, v, a, m, horizon_commitment_digest=d("hara"), epoch=7)
    with pytest.raises(MatrixRealityError, match="different Matrix"):
        hara.assert_sealed(matrix_b, v, a, m)


def test_matrix_cannot_cross_customer_veyra():
    bank_a = veyra("bank-a")
    bank_b = veyra("bank-b")
    matrix = birth_matrix(
        bank_a,
        instance_digest=d("matrix"),
        reality_commitment_digest=d("reality"),
        birth_epoch=7,
    )
    with pytest.raises(MatrixRealityError, match="different Veyra"):
        matrix.assert_sealed(bank_b)


def test_matrix_admission_binds_exact_mir_aevra_hara_and_epoch():
    v = veyra()
    m = mir()
    a = aevra(v, m)
    matrix = birth_matrix(v, instance_digest=d("matrix"), reality_commitment_digest=d("reality"), birth_epoch=7)
    hara = birth_hara(matrix, v, a, m, horizon_commitment_digest=d("hara"), epoch=7)
    admission = admit_matrix_hara(matrix, hara, v, a, m, evidence_digest=d("admission"))
    admission.assert_sealed(matrix, hara, v, a, m)
    assert admission.epoch == 7
    assert admission.native_mir_fingerprint == m.fingerprint


def test_tampered_matrix_admission_fails_closed():
    v = veyra()
    m = mir()
    a = aevra(v, m)
    matrix = birth_matrix(v, instance_digest=d("matrix"), reality_commitment_digest=d("reality"), birth_epoch=7)
    hara = birth_hara(matrix, v, a, m, horizon_commitment_digest=d("hara"), epoch=7)
    admission = admit_matrix_hara(matrix, hara, v, a, m, evidence_digest=d("admission"))
    forged = replace(admission, evidence_digest=d("forged"))
    with pytest.raises(MatrixRealityError, match="seal mismatch"):
        forged.assert_sealed(matrix, hara, v, a, m)
