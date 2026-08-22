from dataclasses import replace

import pytest

from koschei.universe_nuclear_containment_v1 import (
    NuclearContainmentError,
    enter_nuclear_containment,
    require_nuclear_containment,
    required_nuclear_actions,
)
from koschei.universe_state_machine_v1 import initial_universe_state


def _state():
    return initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)


def test_nuclear_containment_contains_every_sigil_and_seals_receipt():
    previous = _state()
    contained, receipt = enter_nuclear_containment(
        previous, cause_evidence_digest="catastrophic-evidence"
    )
    require_nuclear_containment(previous, contained, receipt)
    assert receipt.epoch == 7
    assert not receipt.external_effects_attempted
    assert all(row.state.value == "contained" for row in contained.sigils)
    assert tuple(receipt.completed_actions) == required_nuclear_actions()


def test_nuclear_profile_is_defensive_only():
    previous = _state()
    contained, receipt = enter_nuclear_containment(
        previous, cause_evidence_digest="catastrophic-evidence"
    )
    retaliatory = replace(receipt, external_effects_attempted=True)
    with pytest.raises(NuclearContainmentError):
        require_nuclear_containment(previous, contained, retaliatory)


def test_missing_required_action_fails_closed():
    previous = _state()
    contained, receipt = enter_nuclear_containment(
        previous, cause_evidence_digest="catastrophic-evidence"
    )
    incomplete = replace(receipt, completed_actions=receipt.completed_actions[:-1])
    with pytest.raises(NuclearContainmentError):
        require_nuclear_containment(previous, contained, incomplete)


def test_receipt_cannot_be_moved_to_another_universe_state():
    previous = _state()
    contained, receipt = enter_nuclear_containment(
        previous, cause_evidence_digest="catastrophic-evidence"
    )
    other = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=8)
    with pytest.raises(NuclearContainmentError):
        require_nuclear_containment(other, contained, receipt)
