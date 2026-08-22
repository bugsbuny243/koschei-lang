from pathlib import Path
import tempfile

import pytest

from koschei.native_sigil_epoch_tombstone_v1 import (
    DurableEpochFence,
    EpochTombstoneError,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_request_binding_v1 import seal_effect_request
from koschei.parser import parse
from koschei.universe_rebirth_v1 import rebirth_contained_universe
from koschei.universe_state_machine_v1 import (
    SigilState,
    contain_universe,
    initial_universe_state,
    transition_sigil,
)


def _active_state(epoch: int = 7):
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=epoch)
    for sigil in ("ka", "vor", "shi", "thal", "nur"):
        state = transition_sigil(state, sigil, SigilState.PREPARED, evidence_digest=f"{sigil}-prepare")
        state = transition_sigil(state, sigil, SigilState.SEALED, evidence_digest=f"{sigil}-seal")
        state = transition_sigil(state, sigil, SigilState.ACTIVE, evidence_digest=f"{sigil}-active")
    return state


def _mir():
    return lower_native_sigils(parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;"))


def _request(epoch: int, nonce: str):
    mir = _mir()
    return seal_effect_request(
        mir,
        effect_id="effect-1",
        subject="withdrawal",
        operation="sign",
        request_digest=f"payload-{nonce}",
        identity_digest="identity-1",
        epoch=epoch,
        nonce_digest=nonce,
    )


def test_rebirth_tombstones_entire_previous_epoch_even_for_new_nonce():
    previous = contain_universe(_active_state(7), evidence_digest="containment")
    fresh, receipt = rebirth_contained_universe(previous, cause_evidence_digest="recovery")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "epochs.sqlite3"
        with DurableEpochFence(path) as fence:
            fence.initialize(previous)
            fence.require_current_request(_request(7, "nonce-before"))
            fence.advance_rebirth(previous, fresh, receipt)

            assert fence.is_tombstoned(previous.activation_plan_digest, 7)
            with pytest.raises(EpochTombstoneError):
                fence.require_current_request(_request(7, "brand-new-nonce"))


def test_fresh_epoch_is_current_after_rebirth():
    previous = contain_universe(_active_state(7), evidence_digest="containment")
    fresh, receipt = rebirth_contained_universe(previous, cause_evidence_digest="recovery")

    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            head = fence.advance_rebirth(previous, fresh, receipt)
            assert head.current_epoch == 8
            fence.require_current_request(_request(8, "nonce-8"))


def test_epoch_tombstone_survives_process_restart():
    previous = contain_universe(_active_state(7), evidence_digest="containment")
    fresh, receipt = rebirth_contained_universe(previous, cause_evidence_digest="recovery")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "epochs.sqlite3"
        fence = DurableEpochFence(path)
        fence.initialize(previous)
        fence.advance_rebirth(previous, fresh, receipt)
        fence.close()

        fence = DurableEpochFence(path)
        assert fence.current(previous.activation_plan_digest).current_epoch == 8
        assert fence.is_tombstoned(previous.activation_plan_digest, 7)
        with pytest.raises(EpochTombstoneError):
            fence.require_current_request(_request(7, "new-after-restart"))
        fence.close()


def test_same_rebirth_cannot_advance_twice():
    previous = contain_universe(_active_state(7), evidence_digest="containment")
    fresh, receipt = rebirth_contained_universe(previous, cause_evidence_digest="recovery")

    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(previous)
            fence.advance_rebirth(previous, fresh, receipt)
            with pytest.raises(Exception):
                fence.advance_rebirth(previous, fresh, receipt)
