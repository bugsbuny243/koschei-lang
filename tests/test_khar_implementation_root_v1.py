from dataclasses import replace
import hashlib

import pytest

from koschei.khar_constitution_v1 import birth_canonical_veyra
from koschei.khar_implementation_root_v1 import (
    KharImplementationRootError,
    build_khar_implementation_measurement,
    seal_khar_implementation_witness,
    verify_khar_implementation_root,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def measurement(*, veyra_digest: str | None = None, epoch: int = 9):
    if veyra_digest is None:
        veyra_digest = canonical_veyra().digest
    return build_khar_implementation_measurement(
        veyra_digest=veyra_digest,
        native_mir_fingerprint=d("native-mir"),
        epoch=epoch,
        compiler_sha256=d("compiler-bytes"),
        runtime_sha256=d("runtime-bytes"),
        native_build_manifest_digest=d("native-build-manifest"),
        release_proof_digest=d("release-proof"),
        maturity_attestation_digest=d("maturity-attestation"),
        ci_head_sha="a" * 40,
    )


def canonical_veyra():
    return birth_canonical_veyra(
        profile_digest=d("profile"),
        genesis_digest=d("genesis"),
        instance_digest=d("customer-a"),
        birth_epoch=1,
    )


def witnesses(measured):
    first_key = b"A" * 32
    second_key = b"B" * 32
    first = seal_khar_implementation_witness(
        measured,
        witness_id="host-measurement",
        failure_root="host-root",
        key=first_key,
    )
    second = seal_khar_implementation_witness(
        measured,
        witness_id="release-verifier",
        failure_root="release-root",
        key=second_key,
    )
    return (first, second), {
        "host-measurement": first_key,
        "release-verifier": second_key,
    }


def test_two_independent_witnesses_mint_authority_free_root():
    veyra = canonical_veyra()
    measured = measurement(veyra_digest=veyra.digest)
    sealed, keys = witnesses(measured)

    root = verify_khar_implementation_root(measured, sealed, witness_keys=keys)

    root.assert_sealed()
    root.assert_for(
        veyra_digest=veyra.digest,
        native_mir_fingerprint=d("native-mir"),
        epoch=9,
    )
    assert root.authority is False
    assert root.witness_ids == ("host-measurement", "release-verifier")
    assert root.failure_roots == ("host-root", "release-root")


def test_one_witness_is_not_an_implementation_root():
    measured = measurement()
    sealed, keys = witnesses(measured)

    with pytest.raises(KharImplementationRootError, match="at least 2"):
        verify_khar_implementation_root(
            measured,
            (sealed[0],),
            witness_keys={sealed[0].witness_id: keys[sealed[0].witness_id]},
        )


def test_two_names_on_one_failure_root_do_not_count_as_independent():
    measured = measurement()
    first_key = b"A" * 32
    second_key = b"B" * 32
    first = seal_khar_implementation_witness(
        measured,
        witness_id="witness-a",
        failure_root="same-machine",
        key=first_key,
    )
    second = seal_khar_implementation_witness(
        measured,
        witness_id="witness-b",
        failure_root="same-machine",
        key=second_key,
    )

    with pytest.raises(KharImplementationRootError, match="independent failure roots"):
        verify_khar_implementation_root(
            measured,
            (first, second),
            witness_keys={"witness-a": first_key, "witness-b": second_key},
        )


def test_measurement_tampering_invalidates_all_existing_witnesses():
    measured = measurement()
    sealed, keys = witnesses(measured)
    tampered = replace(measured, runtime_sha256=d("attacker-runtime"))

    with pytest.raises(KharImplementationRootError, match="measurement seal mismatch"):
        verify_khar_implementation_root(tampered, sealed, witness_keys=keys)


def test_resealed_different_measurement_cannot_replay_old_witnesses():
    veyra = canonical_veyra()
    measured = measurement(veyra_digest=veyra.digest, epoch=9)
    sealed, keys = witnesses(measured)
    later = measurement(veyra_digest=veyra.digest, epoch=10)

    with pytest.raises(KharImplementationRootError, match="different measurement"):
        verify_khar_implementation_root(later, sealed, witness_keys=keys)


def test_verified_root_cannot_move_to_another_veyra_mir_or_epoch():
    veyra = canonical_veyra()
    measured = measurement(veyra_digest=veyra.digest, epoch=9)
    sealed, keys = witnesses(measured)
    root = verify_khar_implementation_root(measured, sealed, witness_keys=keys)

    other = birth_canonical_veyra(
        profile_digest=d("profile"),
        genesis_digest=d("genesis"),
        instance_digest=d("customer-b"),
        birth_epoch=1,
    )
    with pytest.raises(KharImplementationRootError, match="different Veyra"):
        root.assert_for(
            veyra_digest=other.digest,
            native_mir_fingerprint=d("native-mir"),
            epoch=9,
        )
    with pytest.raises(KharImplementationRootError, match="different native MIR"):
        root.assert_for(
            veyra_digest=veyra.digest,
            native_mir_fingerprint=d("other-native-mir"),
            epoch=9,
        )
    with pytest.raises(KharImplementationRootError, match="different epoch"):
        root.assert_for(
            veyra_digest=veyra.digest,
            native_mir_fingerprint=d("native-mir"),
            epoch=10,
        )


def test_wrong_external_witness_key_is_rejected():
    measured = measurement()
    sealed, keys = witnesses(measured)
    forged_keys = dict(keys)
    forged_keys[sealed[1].witness_id] = b"Z" * 32

    with pytest.raises(KharImplementationRootError, match="MAC is invalid"):
        verify_khar_implementation_root(measured, sealed, witness_keys=forged_keys)
