"""Adversarial and persistence tests for durable, single-ledger portal replay.

Proof identity is public. Tests do not imply issuer authentication, permission
to execute an effect, or transactional exactly-once side effects.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
import tempfile

import pytest

from koschei.matrix_portal_replay_v1 import (
    DurablePortalReplayFence, PortalReplayFenceError,
)
from koschei.matrix_portal_transit_v1 import create_portal_transit_proof_v1
from koschei.wanda_reality_integrity_v1 import commit_reality_v1


def fixture(payload: bytes = b"p" * 32):
    source = commit_reality_v1(
        reality_id="BANK-A", epoch=7,
        state_digest=b"s" * 32, authority_digest=b"a" * 32,
    )
    destination = commit_reality_v1(
        reality_id="EXCHANGE-B", epoch=9,
        state_digest=b"d" * 32, authority_digest=b"b" * 32,
    )
    kwargs = {
        "source": source,
        "destination": destination,
        "payload_digest": payload,
        "effect": "submit",
        "target_digest": b"t" * 32,
        "epoch": 11,
    }
    proof = create_portal_transit_proof_v1(**kwargs)
    return proof, kwargs


def test_durable_replay_rejected_after_close_and_restart():
    proof, args = fixture()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "portal.sqlite3"
        with DurablePortalReplayFence(path) as fence:
            assert not fence.is_consumed(proof.transit_digest)
            assert fence.consume(proof, **args) is None
            assert fence.is_consumed(proof.transit_digest)
            with pytest.raises(PortalReplayFenceError, match="already consumed"):
                fence.consume(proof, **args)
        with DurablePortalReplayFence(path) as reopened:
            assert reopened.is_consumed(proof.transit_digest)
            with pytest.raises(PortalReplayFenceError, match="already consumed"):
                reopened.consume(proof, **args)
            other, other_args = fixture(b"x" * 32)
            assert other.transit_digest != proof.transit_digest
            reopened.consume(other, **other_args)
            assert reopened.is_consumed(other.transit_digest)
            assert reopened.is_consumed(proof.transit_digest)


def test_forged_digest_state_effect_target_and_epoch_do_not_burn_proof():
    proof, args = fixture()
    with DurablePortalReplayFence(":memory:") as fence:
        def denied(candidate, **overrides):
            values = dict(args)
            values.update(overrides)
            with pytest.raises(PortalReplayFenceError, match="canonical"):
                fence.consume(candidate, **values)
            assert not fence.is_consumed(proof.transit_digest)

        denied(replace(proof, transit_digest=b"x" * 32))
        denied(replace(proof, payload_digest=b"z" * 32))
        denied(replace(proof, effect="transfer"))
        denied(replace(proof, epoch=99))
        denied(proof, effect="transfer")
        denied(proof, target_digest=b"z" * 32)
        denied(proof, epoch=12)
        denied(proof, payload_digest=b"z" * 32)
        denied(proof, source=replace(args["source"], state_digest=b"z" * 32))
        denied(proof, destination=replace(args["destination"], epoch=10))

        with pytest.raises(PortalReplayFenceError, match="32 bytes"):
            fence.is_consumed(b"no")
        fence.consume(proof, **args)
        assert fence.is_consumed(proof.transit_digest)


def test_two_database_handles_compete_atomically_for_same_proof():
    proof, args = fixture()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "portal.sqlite3"
        with DurablePortalReplayFence(path) as first, DurablePortalReplayFence(path) as second:
            barrier = Barrier(2)
            def attempt(fence):
                barrier.wait(timeout=15)
                try:
                    fence.consume(proof, **args)
                    return "accepted"
                except PortalReplayFenceError as error:
                    assert "already consumed" in str(error)
                    return "replayed"
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(attempt, first),
                           executor.submit(attempt, second)]
                decisions = sorted(future.result(timeout=20) for future in futures)
            assert decisions == ["accepted", "replayed"]
            assert first.is_consumed(proof.transit_digest)
            assert second.is_consumed(proof.transit_digest)
        with DurablePortalReplayFence(path) as third:
            assert third.is_consumed(proof.transit_digest)
            with pytest.raises(PortalReplayFenceError):
                third.consume(proof, **args)


def test_integrity_failure_and_duplicate_do_not_poison_later_transaction():
    proof, args = fixture()
    another, other_args = fixture(b"k" * 32)
    with DurablePortalReplayFence(":memory:") as fence:
        with pytest.raises(PortalReplayFenceError):
            fence.consume(replace(proof, transit_digest=b"f" * 32), **args)
        fence.consume(proof, **args)
        with pytest.raises(PortalReplayFenceError):
            fence.consume(proof, **args)
        fence.consume(another, **other_args)
        assert fence.is_consumed(another.transit_digest)


def test_ledger_grants_no_authority_and_has_no_external_effect_executor():
    proof, args = fixture()
    with DurablePortalReplayFence(":memory:") as fence:
        assert not hasattr(fence, "execute")
        assert not hasattr(fence, "grant")
        assert not hasattr(fence, "send")
        # The caller can burn a valid but NOT externally authorized proof.
        # Therefore the caller's authentication and authorization MUST occur
        # before this mutation, in a trusted service boundary.
        fence.consume(proof, **args)
        with pytest.raises(PortalReplayFenceError):
            fence.consume(proof, **args)
