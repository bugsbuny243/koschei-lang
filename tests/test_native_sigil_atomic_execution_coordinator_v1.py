from pathlib import Path
import tempfile
import unittest

from koschei.native_sigil_atomic_execution_coordinator_v1 import (
    AtomicExecutionCoordinator,
    AtomicExecutionCoordinatorError,
)
from koschei.universe_nuclear_containment_v1 import enter_nuclear_containment
from koschei.universe_rebirth_v1 import rebirth_contained_universe
from koschei.universe_state_machine_v1 import initial_universe_state


class _Request:
    def __init__(self, *, plan: str, epoch: int, digest: str) -> None:
        self.universe_plan_digest = plan
        self.epoch = epoch
        self.digest = digest


class AtomicExecutionCoordinatorTests(unittest.TestCase):
    def test_epoch_check_and_replay_claim_are_one_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
            path = Path(directory) / "execution.sqlite3"
            with AtomicExecutionCoordinator(path) as coordinator:
                coordinator.initialize(state)
                request = _Request(plan=state.activation_plan_digest, epoch=7, digest="request-1")
                first = coordinator.atomic_claim(request, "proof-1")
                self.assertEqual(first.state, "CLAIMED")
                with self.assertRaises(AtomicExecutionCoordinatorError):
                    coordinator.atomic_claim(request, "proof-1")

    def test_nuclear_containment_atomically_freezes_and_tombstones_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
            contained, receipt = enter_nuclear_containment(
                state, cause_evidence_digest="catastrophic-evidence"
            )
            path = Path(directory) / "execution.sqlite3"
            with AtomicExecutionCoordinator(path) as coordinator:
                coordinator.initialize(state)
                head = coordinator.apply_nuclear_containment(state, contained, receipt)
                self.assertTrue(head.frozen)
                self.assertEqual(head.current_epoch, 7)
                with self.assertRaises(AtomicExecutionCoordinatorError):
                    coordinator.atomic_claim(
                        _Request(
                            plan=state.activation_plan_digest,
                            epoch=7,
                            digest="brand-new-request-after-containment",
                        ),
                        "proof-new",
                    )

    def test_verified_rebirth_reopens_only_new_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=7)
            contained, nuclear = enter_nuclear_containment(
                state, cause_evidence_digest="catastrophic-evidence"
            )
            fresh, rebirth = rebirth_contained_universe(
                contained, cause_evidence_digest="independent-recovery-proof"
            )
            path = Path(directory) / "execution.sqlite3"
            with AtomicExecutionCoordinator(path) as coordinator:
                coordinator.initialize(state)
                coordinator.apply_nuclear_containment(state, contained, nuclear)
                head = coordinator.advance_rebirth(contained, fresh, rebirth)
                self.assertFalse(head.frozen)
                self.assertEqual(head.current_epoch, 8)

                claim = coordinator.atomic_claim(
                    _Request(plan=state.activation_plan_digest, epoch=8, digest="request-epoch-8"),
                    "proof-8",
                )
                self.assertEqual(claim.epoch, 8)

                with self.assertRaises(AtomicExecutionCoordinatorError):
                    coordinator.atomic_claim(
                        _Request(plan=state.activation_plan_digest, epoch=7, digest="new-old-epoch-request"),
                        "proof-old",
                    )

    def test_freeze_survives_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=3)
            contained, receipt = enter_nuclear_containment(
                state, cause_evidence_digest="catastrophic-evidence"
            )
            path = Path(directory) / "execution.sqlite3"
            coordinator = AtomicExecutionCoordinator(path)
            coordinator.initialize(state)
            coordinator.apply_nuclear_containment(state, contained, receipt)
            coordinator.close()

            coordinator = AtomicExecutionCoordinator(path)
            head = coordinator.current(state.activation_plan_digest)
            self.assertIsNotNone(head)
            self.assertTrue(head.frozen)
            with self.assertRaises(AtomicExecutionCoordinatorError):
                coordinator.atomic_claim(
                    _Request(plan=state.activation_plan_digest, epoch=3, digest="request-after-restart"),
                    "proof",
                )
            coordinator.close()


if __name__ == "__main__":
    unittest.main()
