import pytest

from koschei.vormir_sacrifice_v1 import (
    VormirSacrificeError,
    admits_vormir_root_v1,
    commit_sacrifice_v1,
)

P = b"p" * 32
A = b"a" * 32
H = b"h" * 32
V = b"v" * 32


def make():
    return commit_sacrifice_v1(
        principal_digest=P,
        artifact_digest=A,
        surrendered_authority="network:egress",
        requested_authority="root:sign",
        prior_epoch=7,
        next_epoch=8,
        hardware_attestation_digest=H,
        verifier_digest=V,
    )


def test_valid_sacrifice_binds_principal_artifact_authorities_and_epoch():
    c = make()
    assert len(c.commitment_digest) == 32
    assert c.surrendered_authority == "network:egress"
    assert c.requested_authority == "root:sign"
    assert c.next_epoch == 8


def test_same_authority_is_not_a_sacrifice():
    with pytest.raises(VormirSacrificeError):
        commit_sacrifice_v1(principal_digest=P, artifact_digest=A,
            surrendered_authority="root:sign", requested_authority="root:sign",
            prior_epoch=1, next_epoch=2, hardware_attestation_digest=H,
            verifier_digest=V)


def test_epoch_cannot_skip_or_replay():
    with pytest.raises(VormirSacrificeError):
        commit_sacrifice_v1(principal_digest=P, artifact_digest=A,
            surrendered_authority="network", requested_authority="root:sign",
            prior_epoch=7, next_epoch=9, hardware_attestation_digest=H,
            verifier_digest=V)


def test_admission_requires_actual_revocation_and_matching_reality():
    c = make()
    assert admits_vormir_root_v1(c, revoked_authority="network:egress",
        observed_epoch=8, observed_artifact_digest=A)
    assert not admits_vormir_root_v1(c, revoked_authority="network:egress",
        observed_epoch=7, observed_artifact_digest=A)
    assert not admits_vormir_root_v1(c, revoked_authority="process:spawn",
        observed_epoch=8, observed_artifact_digest=A)
    assert not admits_vormir_root_v1(c, revoked_authority="network:egress",
        observed_epoch=8, observed_artifact_digest=b"x" * 32)


def test_no_raw_personal_device_identifier_surface():
    c = make()
    fields = set(c.__dataclass_fields__)
    assert "mac" not in fields
    assert "imei" not in fields
    assert "serial" not in fields
    assert "device_id" not in fields
