from dataclasses import replace

import pytest

from koschei.decoy_view_broker_v1 import DecoyViewError, require_canonical_build_view
from koschei.protected_source_envelope_v1 import (
    BUILD_SCOPE,
    MATERIALIZE_CAPABILITY,
    BuildAuthorization,
    ProtectedSourceEnvelopeError,
    TrustPlanePolicy,
    create_protected_source_envelope,
    issue_build_authorization,
    materialize_canonical_source,
    verify_envelope_integrity,
)


PROJECT = "koschei-envelope-test"
OID = "a1" * 16
POLICY_HASH = "sha256:" + ("b2" * 32)
INTEGRITY_KEY = b"i" * 32
AUTHORIZATION_KEY = b"a" * 32
CANONICAL_VIEW_KEY = b"v" * 32
CANONICAL = b"fn main() -> Int { return 41 + 1; }\n"
SEALED = b"sealed-v1:" + CANONICAL[::-1]


def decryptor(cipher_suite_id: str, wrapped_data_key_ref: str, artifact: bytes) -> bytearray:
    assert cipher_suite_id == "test-sealed-v1"
    assert wrapped_data_key_ref == "kms://test/project-key/7"
    assert artifact.startswith(b"sealed-v1:")
    return bytearray(artifact[len(b"sealed-v1:") :][::-1])


def envelope():
    return create_protected_source_envelope(
        project_id=PROJECT,
        object_id=OID,
        canonical_source=CANONICAL,
        protected_artifact=SEALED,
        cipher_suite_id="test-sealed-v1",
        wrapped_data_key_ref="kms://test/project-key/7",
        policy_hash=POLICY_HASH,
        integrity_key=INTEGRITY_KEY,
    )


def policy():
    return TrustPlanePolicy(
        project_id=PROJECT,
        policy_hash=POLICY_HASH,
        capabilities=(MATERIALIZE_CAPABILITY,),
    )


def grant(*, start=10, end=12, scope=BUILD_SCOPE, project_id=PROJECT, object_id=OID,
          policy_hash=POLICY_HASH):
    return issue_build_authorization(
        project_id=project_id,
        object_id=object_id,
        policy_hash=policy_hash,
        not_before_epoch=start,
        expires_after_epoch=end,
        nonce="build-session-0001",
        authorization_key=AUTHORIZATION_KEY,
        scope=scope,
    )


def materialize(env=None, *, current_policy=None, auth=None, artifact=SEALED, epoch=11,
                audit_sink=None, decrypt=decryptor):
    return materialize_canonical_source(
        envelope() if env is None else env,
        protected_artifact=artifact,
        policy=policy() if current_policy is None else current_policy,
        build_authorization=grant() if auth is None else auth,
        epoch=epoch,
        integrity_key=INTEGRITY_KEY,
        authorization_key=AUTHORIZATION_KEY,
        canonical_view_key=CANONICAL_VIEW_KEY,
        decryptor=decrypt,
        audit_sink=audit_sink,
    )


def test_authorized_materialization_enters_existing_canonical_build_gate():
    view = materialize()

    assert view.content == CANONICAL
    assert view.provenance == "canonical"
    assert view.deployable is True
    require_canonical_build_view(
        view,
        canonical_view_key=CANONICAL_VIEW_KEY,
        expected_project_id=PROJECT,
        expected_object_id=OID,
        expected_epoch=11,
    )


def test_envelope_validity_is_independent_from_expired_build_authorization():
    env = envelope()
    verify_envelope_integrity(env, protected_artifact=SEALED, integrity_key=INTEGRITY_KEY)

    with pytest.raises(ProtectedSourceEnvelopeError, match="not valid for current epoch"):
        materialize(env, auth=grant(start=1, end=2), epoch=11)

    # The durable artifact/envelope is still cryptographically valid.
    verify_envelope_integrity(env, protected_artifact=SEALED, integrity_key=INTEGRITY_KEY)


def test_wrong_scope_build_authorization_fails_closed():
    with pytest.raises(ProtectedSourceEnvelopeError, match="wrong scope"):
        materialize(auth=grant(scope="protected-source:read"))


def test_local_policy_requires_explicit_materialization_capability():
    no_capability = TrustPlanePolicy(
        project_id=PROJECT,
        policy_hash=POLICY_HASH,
        capabilities=(),
    )
    with pytest.raises(ProtectedSourceEnvelopeError, match="capability is missing"):
        materialize(current_policy=no_capability)


def test_protected_project_cannot_downgrade_to_plaintext_lane():
    downgraded = TrustPlanePolicy(
        project_id=PROJECT,
        policy_hash=POLICY_HASH,
        capabilities=(MATERIALIZE_CAPABILITY,),
        protected_source_required=False,
    )
    with pytest.raises(ProtectedSourceEnvelopeError, match="downgrade"):
        materialize(current_policy=downgraded)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda env: replace(env, policy_hash="sha256:" + ("c3" * 32)),
        lambda env: replace(env, canonical_artifact_hash="sha256:" + ("d4" * 32)),
        lambda env: replace(env, cipher_suite_id=env.cipher_suite_id + "-tampered"),
        lambda env: replace(env, wrapped_data_key_ref=env.wrapped_data_key_ref + "-tampered"),
    ],
)
def test_one_field_envelope_tamper_fails_integrity(mutator):
    with pytest.raises(ProtectedSourceEnvelopeError, match="integrity mismatch"):
        verify_envelope_integrity(
            mutator(envelope()),
            protected_artifact=SEALED,
            integrity_key=INTEGRITY_KEY,
        )


def test_one_bit_protected_artifact_tamper_fails_before_decrypt():
    tampered = bytearray(SEALED)
    tampered[-1] ^= 1
    called = False

    def must_not_decrypt(*args):
        nonlocal called
        called = True
        return bytearray(CANONICAL)

    with pytest.raises(ProtectedSourceEnvelopeError, match="protected artifact hash mismatch"):
        materialize(artifact=bytes(tampered), decrypt=must_not_decrypt)
    assert called is False


def test_canonical_plaintext_hash_mismatch_fails_and_temp_buffer_is_wiped():
    plaintext = bytearray(CANONICAL)
    plaintext[-2] ^= 1

    def wrong_plaintext(*args):
        return plaintext

    with pytest.raises(ProtectedSourceEnvelopeError, match="canonical artifact hash mismatch"):
        materialize(decrypt=wrong_plaintext)
    assert plaintext == bytearray(len(plaintext))


def test_decryptor_must_return_wipeable_plaintext():
    def immutable_plaintext(*args):
        return CANONICAL

    with pytest.raises(ProtectedSourceEnvelopeError, match="mutable bytearray"):
        materialize(decrypt=immutable_plaintext)


def test_build_authorization_is_bound_to_project_object_and_policy():
    other_oid = "c4" * 16
    wrong_object_grant = grant(object_id=other_oid)
    with pytest.raises(ProtectedSourceEnvelopeError, match="object mismatch"):
        materialize(auth=wrong_object_grant)

    other_policy = "sha256:" + ("e5" * 32)
    wrong_policy_grant = grant(policy_hash=other_policy)
    with pytest.raises(ProtectedSourceEnvelopeError, match="policy mismatch"):
        materialize(auth=wrong_policy_grant)


def test_forged_build_authorization_mac_fails_closed():
    valid = grant()
    forged = replace(valid, mac=("0" if valid.mac[0] != "0" else "1") + valid.mac[1:])
    with pytest.raises(ProtectedSourceEnvelopeError, match="MAC is invalid"):
        materialize(auth=forged)


def test_decoy_source_view_still_cannot_cross_canonical_gate():
    from koschei.decoy_view_broker_v1 import read_source_view

    decoy = read_source_view(
        project_id=PROJECT,
        object_id=OID,
        epoch=11,
        authorized=False,
        canonical_reader=lambda oid: CANONICAL,
        deception_key=b"d" * 32,
        canonical_view_key=CANONICAL_VIEW_KEY,
    )
    with pytest.raises(DecoyViewError, match="decoy/non-canonical"):
        require_canonical_build_view(
            decoy,
            canonical_view_key=CANONICAL_VIEW_KEY,
            expected_project_id=PROJECT,
            expected_object_id=OID,
            expected_epoch=11,
        )


def test_audit_contains_attempt_metadata_but_not_source_or_keys():
    events = []
    view = materialize(audit_sink=events.append)
    assert view.content == CANONICAL
    assert len(events) == 1
    event = events[0]
    assert event.outcome == "admitted"
    assert event.project_id == PROJECT
    assert event.object_id == OID
    rendered = repr(event)
    assert CANONICAL.decode().strip() not in rendered
    assert INTEGRITY_KEY.hex() not in rendered
    assert AUTHORIZATION_KEY.hex() not in rendered


def test_unknown_envelope_version_fails_closed():
    with pytest.raises(ProtectedSourceEnvelopeError, match="unsupported"):
        verify_envelope_integrity(
            replace(envelope(), version=2),
            protected_artifact=SEALED,
            integrity_key=INTEGRITY_KEY,
        )
