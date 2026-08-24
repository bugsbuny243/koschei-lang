from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.matrix_horizon_fence_v1 import (
    DurableMatrixHorizonFence,
    MatrixHorizonFenceError,
)
from koschei.matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.parser import parse


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def world():
    mir = lower_native_sigils(parse("ka treasury; vor withdrawal; shi evidence;"))
    veyra = birth_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
        instance_digest=d("bank-a"),
        birth_epoch=7,
    )
    aevra = birth_aevra(
        veyra,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=d("birth"),
        birth_epoch=7,
    )
    matrix_a = birth_matrix(
        veyra,
        instance_digest=d("matrix-a"),
        reality_commitment_digest=d("reality-a"),
        birth_epoch=7,
    )
    hara_a = birth_hara(
        matrix_a,
        veyra,
        aevra,
        mir,
        horizon_commitment_digest=d("hara-a"),
        epoch=7,
    )
    admission_a = admit_matrix_hara(
        matrix_a, hara_a, veyra, aevra, mir, evidence_digest=d("admit-a")
    )
    matrix_b = birth_matrix(
        veyra,
        instance_digest=d("matrix-b"),
        reality_commitment_digest=d("reality-b"),
        birth_epoch=8,
    )
    hara_b = birth_hara(
        matrix_b,
        veyra,
        aevra,
        mir,
        horizon_commitment_digest=d("hara-b"),
        epoch=8,
    )
    admission_b = admit_matrix_hara(
        matrix_b, hara_b, veyra, aevra, mir, evidence_digest=d("admit-b")
    )
    return admission_a, admission_b


def test_cross_matrix_transition_tombstones_old_hara_and_advances_current():
    old, new = world()
    with tempfile.TemporaryDirectory() as directory:
        with DurableMatrixHorizonFence(Path(directory) / "matrix.sqlite3") as fence:
            fence.initialize(old)
            fence.require_current(old)
            head = fence.advance(old, new, cause_digest=d("move"))
            assert head.hara_digest == new.hara_digest
            assert head.matrix_digest == new.matrix_digest
            assert head.epoch == 8
            assert fence.is_tombstoned(old.hara_digest)
            fence.require_current(new)
            with pytest.raises(MatrixHorizonFenceError, match="Morth"):
                fence.require_current(old)


def test_old_hara_death_survives_process_restart():
    old, new = world()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "matrix.sqlite3"
        fence = DurableMatrixHorizonFence(path)
        fence.initialize(old)
        fence.advance(old, new, cause_digest=d("move"))
        fence.close()

        fence = DurableMatrixHorizonFence(path)
        try:
            assert fence.is_tombstoned(old.hara_digest)
            fence.require_current(new)
            with pytest.raises(MatrixHorizonFenceError):
                fence.require_current(old)
        finally:
            fence.close()


def test_cross_matrix_transition_requires_next_epoch():
    old, new = world()
    invalid = type(new)(
        new.matrix_digest,
        new.hara_digest,
        new.aevra_digest,
        new.veyra_digest,
        new.native_mir_fingerprint,
        9,
        new.evidence_digest,
        new.digest,
        new.version,
    )
    with tempfile.TemporaryDirectory() as directory:
        with DurableMatrixHorizonFence(Path(directory) / "matrix.sqlite3") as fence:
            fence.initialize(old)
            with pytest.raises(MatrixHorizonFenceError, match="exactly one next epoch"):
                fence.advance(old, invalid, cause_digest=d("move"))


def test_same_matrix_is_not_a_cross_matrix_transition():
    old, _ = world()
    fake_new_hara = d("other-hara")
    successor = type(old)(
        old.matrix_digest,
        fake_new_hara,
        old.aevra_digest,
        old.veyra_digest,
        old.native_mir_fingerprint,
        8,
        d("new-evidence"),
        d("fake-admission"),
        old.version,
    )
    with tempfile.TemporaryDirectory() as directory:
        with DurableMatrixHorizonFence(Path(directory) / "matrix.sqlite3") as fence:
            fence.initialize(old)
            with pytest.raises(MatrixHorizonFenceError, match="different Matrix"):
                fence.advance(old, successor, cause_digest=d("move"))


def test_same_transition_cannot_be_replayed():
    old, new = world()
    with tempfile.TemporaryDirectory() as directory:
        with DurableMatrixHorizonFence(Path(directory) / "matrix.sqlite3") as fence:
            fence.initialize(old)
            fence.advance(old, new, cause_digest=d("move"))
            with pytest.raises(MatrixHorizonFenceError):
                fence.advance(old, new, cause_digest=d("move-again"))
