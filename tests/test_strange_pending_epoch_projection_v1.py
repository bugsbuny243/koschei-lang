"""Pending, non-authoritative next epoch representation parity and negative tests."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_native_admission_v1 import (
    StrangeNativeAdmissionError,
    issue_strange_native_attestation_v1,
)
from koschei.strange_pending_epoch_projection_v1 import (
    PendingStrangeProjectionV1,
    StrangePendingRepresentationError,
    project_next_strange_epoch_go_v1,
)
from koschei.strange_representation_epoch_v1 import (
    project_strange_epoch_go_v1,
)

ROOT = Path(__file__).resolve().parents[1]


class StrangePendingProjectionV1Tests(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.workdir.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.workdir.name) / "continuity.sqlite3",
            continuity_id="tenant-a",
        )
        self.addCleanup(self.store.close)
        self.now = 599
        self.store.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        self.params = dict(
            continuity_store=self.store,
            trust_plane_seed=b"S" * 32,
            expected_current_epoch=4,
            expected_current_start_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
        )

    def project(self, **changes):
        return project_next_strange_epoch_go_v1(self.mir, **(self.params | changes))

    def test_future_projection_matches_exact_active_epoch_without_authority(self):
        pending_source, candidate = self.project()
        self.assertIsInstance(candidate, PendingStrangeProjectionV1)
        self.assertFalse(candidate.authority)
        self.assertEqual((candidate.previous_epoch, candidate.target_epoch), (4, 5))
        self.assertEqual((candidate.starts_at_seconds, candidate.expires_before_seconds), (600, 720))
        self.assertEqual((pending_source, candidate), self.project())
        # Cannot accidentally feed a pending candidate to the public native
        # issuer; this is NOT an active StrangeEpochProjectionV1.
        with self.assertRaises(StrangeNativeAdmissionError):
            issue_strange_native_attestation_v1(
                receipt=candidate,
                native_binary=b"nonempty",
                deployment_id="tenant-a/worker",
                veyra_digest="a" * 64,
                mir_fingerprint=self.mir.fingerprint,
                continuity=self.store.as_continuity_authority(),
                expected_epoch=5,
                starts_at_seconds=600,
                seconds_reader=lambda: 600,
                attestation_key=b"A" * 32,
            )
        self.store.advance(
            expected_current_epoch=4,
            next_epoch=5,
            starts_at_seconds=600,
            observed_seconds=600,
        )
        self.now = 600
        active_source, active = project_strange_epoch_go_v1(
            self.mir,
            trust_plane_seed=b"S" * 32,
            continuity=self.store.as_continuity_authority(),
            expected_epoch=5,
            starts_at_seconds=600,
            seconds_reader=lambda: self.now,
            deployment_id="tenant-a/worker",
            veyra_digest="a" * 64,
        )
        self.assertEqual(pending_source, active_source)
        self.assertEqual(candidate.source_sha256, active.source_sha256)

    def test_prep_does_not_advance_epoch_and_is_scoped(self):
        source, _ = self.project()
        different_tenant, _ = self.project(deployment_id="tenant-b/worker")
        different_veyra, _ = self.project(veyra_digest="b" * 64)
        different_key, _ = self.project(trust_plane_seed=b"Z" * 32)
        self.assertEqual(self.store.read_snapshot().epoch, 4)
        self.assertNotEqual(source, different_tenant)
        self.assertNotEqual(source, different_veyra)
        self.assertNotEqual(source, different_key)

    def test_preparation_rejected_at_boundary_or_after_epoch_drift(self):
        self.now = 600
        with self.assertRaises(StrangePendingRepresentationError):
            self.project()
        self.store.advance(
            expected_current_epoch=4, next_epoch=5,
            starts_at_seconds=600, observed_seconds=600,
        )
        self.now = 599
        with self.assertRaises(StrangePendingRepresentationError):
            self.project()

    def test_future_clock_forgery_and_bad_inputs_fail_closed(self):
        for change in (
            dict(seconds_reader=lambda: True),
            dict(seconds_reader=lambda: (_ for _ in ()).throw(OSError("offline"))),
            dict(veyra_digest="Z" * 64),
            dict(trust_plane_seed=b"short"),
            dict(expected_current_epoch=5),
            dict(expected_current_start_seconds=481),
            dict(deployment_id=""),
        ):
            with self.subTest(change=change), self.assertRaises(StrangePendingRepresentationError):
                self.project(**change)

    def test_epoch_change_while_projecting_discards_pending_source(self):
        from koschei.mir_go_native import generate_go_mir_native

        def rotate_mid_build(mir, *, representation_seed=None):
            source = generate_go_mir_native(mir, representation_seed=representation_seed)
            self.store.advance(
                expected_current_epoch=4, next_epoch=5,
                starts_at_seconds=600, observed_seconds=600,
            )
            return source

        with patch(
            "koschei.strange_pending_epoch_projection_v1.generate_go_mir_native",
            side_effect=rotate_mid_build,
        ):
            with self.assertRaises(StrangePendingRepresentationError):
                self.project()

    def test_clock_rollback_within_projection_fails_closed(self):
        readings = iter((599, 598))
        with self.assertRaises(StrangePendingRepresentationError):
            self.project(seconds_reader=lambda: next(readings))


if __name__ == "__main__":
    unittest.main()
