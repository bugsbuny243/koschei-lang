from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

import pytest

from koschei.native_sigil_atomic_execution_coordinator_v1 import (
    AtomicExecutionCoordinator,
    AtomicExecutionCoordinatorError,
)
from koschei.native_sigil_epoch_tombstone_v1 import DurableEpochFence
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_request_binding_v1 import (
    NativeSigilRequestBindingError,
    seal_effect_request,
)
from koschei.parser import parse
from koschei.universe_state_machine_v1 import initial_universe_state


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def mir():
    return lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )


def request(m, epoch=7):
    return seal_effect_request(
        m,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d("payload"),
        identity_digest=d("identity"),
        epoch=epoch,
        nonce_digest=d("nonce"),
    )


def test_canonical_request_activation_identity_matches_universe_state():
    m = mir()
    req = request(m)
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    assert req.universe_plan_digest == m.universe_plan_digest
    assert req.activation_plan_digest == state.activation_plan_digest
    assert req.universe_plan_digest != req.activation_plan_digest


def test_real_canonical_request_passes_durable_epoch_fence():
    m = mir()
    req = request(m)
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    with tempfile.TemporaryDirectory() as directory:
        with DurableEpochFence(Path(directory) / "epochs.sqlite3") as fence:
            fence.initialize(state)
            fence.require_current_request(req)


def test_real_canonical_request_can_be_atomically_claimed_once():
    m = mir()
    req = request(m)
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
    with tempfile.TemporaryDirectory() as directory:
        with AtomicExecutionCoordinator(Path(directory) / "execution.sqlite3") as coordinator:
            coordinator.initialize(state)
            claim = coordinator.atomic_claim(req, d("proof"))
            assert claim.activation_plan_digest == req.activation_plan_digest
            assert claim.state == "CLAIMED"
            with pytest.raises(AtomicExecutionCoordinatorError):
                coordinator.atomic_claim(req, d("proof"))


def test_activation_identity_tamper_breaks_request_seal():
    m = mir()
    req = request(m)
    forged = replace(req, activation_plan_digest=d("other-plan"))
    with pytest.raises(NativeSigilRequestBindingError, match="activation-plan"):
        forged.assert_sealed(m)
