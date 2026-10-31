"""Atomic staged next-epoch handoff: restart, CAS, tamper and expiry tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_epoch_handoff_v1 import (
    StrangeEpochHandoffError,
    StrangeEpochHandoffV1,
)
from koschei.strange_representation_epoch_v1 import (
    StrangeRepresentationEpochError,
    require_strange_epoch_window_v1,
)

KEY = b"H" * 32


class StrangeEpochHandoffV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "continuity.sqlite3"
        self.store = StrangeDurableContinuityV1(self.path, continuity_id="tenant-a")
        self.addCleanup(self.store.close)
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        self.journal = StrangeEpochHandoffV1(self.store)
        self.now = 599

    def stage(self, **kwargs):
        arguments = dict(
            expected_old_epoch=4,
            expected_old_start_seconds=480,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
            mir_fingerprint="b" * 64,
            source_sha256="c" * 64,
            native_binary=b"candidate-next-native-bytes",
            seconds_reader=lambda: self.now,
            handoff_key=KEY,
        )
        arguments.update(kwargs)
        return self.journal.stage(**arguments)

    def activate(self, item, **kwargs):
        arguments = dict(
            expected_old_epoch=4,
            expected_handoff_mac=item.handoff_mac,
            seconds_reader=lambda: self.now,
            handoff_key=KEY,
        )
        arguments.update(kwargs)
        return self.journal.activate(**arguments)

    def test_next_epoch_is_staged_but_not_activated_before_boundary(self):
        item = self.stage()
        self.assertEqual((item.old_epoch, item.next_epoch, item.next_start_seconds), (4, 5, 600))
        self.assertEqual(item.state, "STAGED")
        self.assertFalse(item.authority)
        self.assertEqual(self.store.read_snapshot().epoch, 4)
        with self.assertRaises(ValueError):
            self.activate(item)
        self.assertEqual(self.journal.read(4).state, "STAGED")
        self.assertFalse(self.journal.retired(4))
        self.now = 600
        activated = self.activate(item)
        self.assertEqual(activated.state, "ACTIVATED")
        self.assertEqual(self.store.read_snapshot().epoch, 5)
        self.assertEqual(self.store.read_snapshot().starts_at_seconds, 600)
        self.assertEqual(self.journal.read(4).state, "ACTIVATED")
        self.assertTrue(self.journal.retired(4))
        with self.assertRaises(StrangeEpochHandoffError):
            self.activate(item)

    def test_old_epoch_build_gate_rejects_after_atomic_activation(self):
        stage = self.stage()
        self.now = 600
        self.activate(stage)
        authority = self.store.as_continuity_authority()
        with self.assertRaises(StrangeRepresentationEpochError):
            require_strange_epoch_window_v1(
                continuity=authority,
                expected_epoch=4,
                starts_at_seconds=480,
                seconds_reader=lambda: 599,
            )
        self.assertEqual(
            require_strange_epoch_window_v1(
                continuity=authority,
                expected_epoch=5,
                starts_at_seconds=600,
                seconds_reader=lambda: 600,
            ),
            600,
        )

    def test_staging_duplicate_is_rejected_without_changing_binary(self):
        first = self.stage()
        with self.assertRaises(StrangeEpochHandoffError):
            self.stage(native_binary=b"altered-candidate")
        self.assertEqual(self.journal.read(4), first)

    def test_stage_survives_restart_and_can_activate_once(self):
        initial = self.stage()
        with StrangeDurableContinuityV1(self.path, continuity_id="tenant-a") as fresh_store:
            fresh = StrangeEpochHandoffV1(fresh_store)
            self.assertEqual(fresh.read(4), initial)
            self.now = 600
            done = fresh.activate(
                expected_old_epoch=4,
                expected_handoff_mac=initial.handoff_mac,
                seconds_reader=lambda: self.now,
                handoff_key=KEY,
            )
            self.assertEqual(done.state, "ACTIVATED")
            self.assertTrue(fresh.retired(4))
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_wrong_key_or_manifest_digest_never_rotates_epoch(self):
        stage = self.stage()
        self.now = 600
        with self.assertRaises(StrangeEpochHandoffError):
            self.activate(stage, handoff_key=b"B" * 32)
        with self.assertRaises(StrangeEpochHandoffError):
            self.activate(stage, expected_handoff_mac="f" * 64)
        self.assertEqual(self.store.read_snapshot().epoch, 4)
        self.assertFalse(self.journal.retired(4))
        self.activate(stage)

    def test_tampered_staged_deployment_or_binary_digest_fails_closed(self):
        stage = self.stage()
        self.store._db.execute(
            "UPDATE strange_handoffs_v1 SET native_sha256=? "
            "WHERE continuity_id=? AND old_epoch=?",
            ("f" * 64, "tenant-a", 4),
        )
        self.now = 600
        with self.assertRaises(StrangeEpochHandoffError):
            self.activate(stage)
        self.assertEqual(self.store.read_snapshot().epoch, 4)

    def test_expired_new_window_cannot_be_activated(self):
        stage = self.stage()
        self.now = 720
        with self.assertRaises(ValueError):
            self.activate(stage)
        self.assertEqual(self.store.read_snapshot().epoch, 4)
        self.assertFalse(self.journal.retired(4))

    def test_stale_head_or_wrong_tenant_blocks_handoff(self):
        item = self.stage()
        with StrangeDurableContinuityV1(self.path, continuity_id="tenant-b") as other:
            other.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
            wrong_journal = StrangeEpochHandoffV1(other)
            self.now = 600
            with self.assertRaises(StrangeEpochHandoffError):
                wrong_journal.activate(
                    expected_old_epoch=4,
                    expected_handoff_mac=item.handoff_mac,
                    seconds_reader=lambda: self.now,
                    handoff_key=KEY,
                )
        self.store.advance(
            expected_current_epoch=4,
            next_epoch=5,
            starts_at_seconds=600,
            observed_seconds=600,
        )
        with self.assertRaises(StrangeEpochHandoffError):
            self.activate(item)
        self.assertEqual(self.journal.read(4).state, "STAGED")

    def test_two_concurrent_activations_commit_at_most_once(self):
        item = self.stage()
        self.now = 600
        with StrangeDurableContinuityV1(self.path, continuity_id="tenant-a") as other_store:
            other_journal = StrangeEpochHandoffV1(other_store)

            def attempt(journal):
                try:
                    journal.activate(
                        expected_old_epoch=4,
                        expected_handoff_mac=item.handoff_mac,
                        seconds_reader=lambda: self.now,
                        handoff_key=KEY,
                    )
                    return "activated"
                except StrangeEpochHandoffError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(attempt, (self.journal, other_journal)))
        self.assertEqual(sorted(results), ["activated", "rejected"])
        self.assertTrue(self.journal.retired(4))
        self.assertEqual(self.store.read_snapshot().epoch, 5)

    def test_missing_clock_and_bad_stage_inputs_fail_closed(self):
        for changes in (
            dict(seconds_reader=lambda: True),
            dict(seconds_reader=lambda: (_ for _ in ()).throw(OSError("offline"))),
            dict(native_binary=b""),
            dict(expected_old_epoch=5),
            dict(source_sha256="Z" * 64),
            dict(handoff_key=b"short"),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.stage(**changes)
        self.assertEqual(self.store.read_snapshot().epoch, 4)


if __name__ == "__main__":
    unittest.main()
