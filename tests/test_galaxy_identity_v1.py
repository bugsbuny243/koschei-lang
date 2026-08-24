from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import (
    GalaxyIdentityError,
    birth_aevra,
    birth_veyra,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.parser import parse


def _d(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _mir(subject: str = "withdrawal"):
    return lower_native_sigils(parse(f"ka treasury; vor {subject}; shi evidence;"))


def _veyra(instance: str = "bank-a"):
    return birth_veyra(
        profile_digest=_d("banking-profile-v1"),
        genesis_digest=_d("genesis-evidence"),
        constitution_digest=_d("khar-v1"),
        instance_digest=_d(instance),
        birth_epoch=10,
    )


def test_same_language_profile_can_birth_distinct_customer_veyras():
    left = _veyra("bank-a")
    right = _veyra("bank-b")
    assert left.profile_digest == right.profile_digest
    assert left.constitution_digest == right.constitution_digest
    assert left.digest != right.digest


def test_aevra_birth_is_bound_to_veyra_compiler_binding_and_evidence():
    mir = _mir()
    veyra = _veyra()
    aevra = birth_aevra(
        veyra,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=_d("admission-evidence"),
        birth_epoch=10,
    )
    aevra.assert_sealed(veyra, mir)
    assert aevra.veyra_digest == veyra.digest
    assert aevra.native_mir_fingerprint == mir.fingerprint


def test_visible_subject_copy_does_not_transfer_aevra_to_another_veyra():
    mir = _mir()
    original_veyra = _veyra("bank-a")
    copied_veyra = _veyra("bank-b")
    aevra = birth_aevra(
        original_veyra,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=_d("admission-evidence"),
        birth_epoch=10,
    )
    with pytest.raises(GalaxyIdentityError, match="different Veyra"):
        aevra.assert_sealed(copied_veyra, mir)


def test_aevra_cannot_be_rebound_to_a_different_compiler_product():
    veyra = _veyra()
    original = _mir("withdrawal")
    other = _mir("signing")
    aevra = birth_aevra(
        veyra,
        original,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=_d("admission-evidence"),
        birth_epoch=10,
    )
    with pytest.raises(GalaxyIdentityError, match="different compiler product"):
        aevra.assert_sealed(veyra, other)


def test_tampered_aevra_identity_fails_closed():
    mir = _mir()
    veyra = _veyra()
    aevra = birth_aevra(
        veyra,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=_d("admission-evidence"),
        birth_epoch=10,
    )
    tampered = replace(aevra, birth_evidence_digest=_d("forged-evidence"))
    with pytest.raises(GalaxyIdentityError, match="seal mismatch"):
        tampered.assert_sealed(veyra, mir)


def test_aevra_cannot_predate_its_veyra():
    with pytest.raises(GalaxyIdentityError, match="cannot predate"):
        birth_aevra(
            _veyra(),
            _mir(),
            sigil="vor",
            subject="withdrawal",
            birth_evidence_digest=_d("evidence"),
            birth_epoch=9,
        )
