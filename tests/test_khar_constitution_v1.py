from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import birth_veyra
from koschei.khar_constitution_v1 import (
    CANONICAL_KHAR_DIGEST_V1,
    CANONICAL_KHAR_LAWS_V1,
    KharConstitutionError,
    birth_canonical_veyra,
    canonical_khar_v1,
    require_canonical_khar_v1,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def test_canonical_khar_digest_is_derived_from_public_fixed_laws():
    constitution = canonical_khar_v1()
    constitution.assert_canonical()
    assert constitution.laws == CANONICAL_KHAR_LAWS_V1
    assert constitution.digest == CANONICAL_KHAR_DIGEST_V1
    assert len(constitution.digest) == 64


def test_canonical_veyra_is_bound_to_exact_khar_v1():
    veyra = birth_canonical_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        instance_digest=d("bank-a"),
        birth_epoch=7,
    )
    constitution = require_canonical_khar_v1(veyra)
    assert veyra.constitution_digest == constitution.digest


def test_caller_supplied_fake_constitution_cannot_pass_canonical_khar_gate():
    forged = birth_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("attacker-khar"),
        instance_digest=d("bank-a"),
        birth_epoch=7,
    )
    with pytest.raises(KharConstitutionError, match="not bound to the canonical"):
        require_canonical_khar_v1(forged)


def test_canonical_law_set_cannot_be_rewritten_under_v1_identity():
    constitution = canonical_khar_v1()
    weakened = replace(
        constitution,
        laws=tuple(
            "khar.sathra.five-is-enough" if law == "khar.sathra.exact-six" else law
            for law in constitution.laws
        ),
    )
    with pytest.raises(KharConstitutionError, match="substitution"):
        weakened.assert_canonical()


def test_canonical_digest_cannot_be_relabelled_after_birth():
    constitution = canonical_khar_v1()
    tampered = replace(constitution, digest=d("different-laws"))
    with pytest.raises(KharConstitutionError, match="seal mismatch"):
        tampered.assert_canonical()
