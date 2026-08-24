from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.native_sigil_epoch_tombstone_v1 import DurableEpochFence
from koschei.universe_rebirth_v1 import rebirth_contained_universe
from koschei.universe_state_machine_v1 import (
    SigilState,
    contain_universe,
    initial_universe_state,
    transition_sigil,
)
from koschei.vormir_sacrifice_v1 import (
    VormirEpochWitnessV1,
    VormirSacrificeError,
    commit_vormir_epoch_sacrifice_v1,
    require_vormir_epoch_sacrifice_v1,
)


def d32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def active(epoch: int = 7):
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=epoch)
    for sigil in ("ka", "vor", "shi", "thal", "nur"):
        state = transition_sigil(state, sigil, SigilState.PREPARED, evidence_digest=f"{sigil}-prepare")
        state = transition_sigil(state, sigil, SigilState.SEALED, evidence_digest=f"{sigil}-seal")
        state = transition_sigil(state, sigil, SigilState.ACTIVE, evidence_digest=f"{sigil}-active")
    return state


def witnesses():
    return (
        VormirEpochWitnessV1(d32("domain-a"), d32("evidence-a")),
        VormirEpochWitnessV1(d32("domain-b"), d32("evidence-b")),
    )


def staged_rebirth():
    previous = contain_universe(active(7), evidence_digest="containment")
    fresh, rebirth = rebirth_contained_universe(previous, cause_evidence_digest="rebirth")
    return previous, fresh, rebirth


def test_vormir_durably_kills_old_epoch_before_accepting_successor():
    previous, fresh, rebirth = staged_rebirth()
    assert all(row.state is SigilState.INACTIVE for row in fresh.sigils)

    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            receipt = commit_vormir_epoch_sacrifice_v1(
                previous, fresh, rebirth, fence, witnesses=witnesses()
            )
            head = require_vormir_epoch_sacrifice_v1(previous, fresh, rebirth, receipt, fence)

            assert receipt.sacrificed_epoch == 7
            assert receipt.successor_epoch == 8
            assert fence.is_tombstoned(previous.activation_plan_digest, 7)
            assert head.current_epoch == 8


def test_vormir_requires_more_than_one_witness_domain():
    previous, fresh, rebirth = staged_rebirth()
    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            with pytest.raises(VormirSacrificeError, match="at least two"):
                commit_vormir_epoch_sacrifice_v1(
                    previous,
                    fresh,
                    rebirth,
                    fence,
                    witnesses=(VormirEpochWitnessV1(d32("domain-a"), d32("evidence-a")),),
                )


def test_vormir_rejects_two_witnesses_from_same_domain():
    previous, fresh, rebirth = staged_rebirth()
    duplicate_domain = (
        VormirEpochWitnessV1(d32("same-domain"), d32("evidence-a")),
        VormirEpochWitnessV1(d32("same-domain"), d32("evidence-b")),
    )
    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            with pytest.raises(VormirSacrificeError, match="domains must be distinct"):
                commit_vormir_epoch_sacrifice_v1(
                    previous, fresh, rebirth, fence, witnesses=duplicate_domain
                )


def test_vormir_tombstone_survives_process_restart():
    previous, fresh, rebirth = staged_rebirth()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "epochs.sqlite3"
        fence = DurableEpochFence(path)
        fence.initialize(previous)
        receipt = commit_vormir_epoch_sacrifice_v1(
            previous, fresh, rebirth, fence, witnesses=witnesses()
        )
        fence.close()

        fence = DurableEpochFence(path)
        try:
            head = require_vormir_epoch_sacrifice_v1(previous, fresh, rebirth, receipt, fence)
            assert fence.is_tombstoned(previous.activation_plan_digest, 7)
            assert head.current_epoch == 8
        finally:
            fence.close()


def test_same_vormir_sacrifice_cannot_be_committed_twice():
    previous, fresh, rebirth = staged_rebirth()
    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            commit_vormir_epoch_sacrifice_v1(
                previous, fresh, rebirth, fence, witnesses=witnesses()
            )
            with pytest.raises(VormirSacrificeError):
                commit_vormir_epoch_sacrifice_v1(
                    previous, fresh, rebirth, fence, witnesses=witnesses()
                )


def test_tampered_vormir_receipt_fails_closed():
    previous, fresh, rebirth = staged_rebirth()
    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            receipt = commit_vormir_epoch_sacrifice_v1(
                previous, fresh, rebirth, fence, witnesses=witnesses()
            )
            forged = replace(receipt, fresh_state_digest="0" * 64)
            with pytest.raises(VormirSacrificeError):
                require_vormir_epoch_sacrifice_v1(previous, fresh, rebirth, forged, fence)
