"""Negative and parity tests for provisional 120-second Strange build windows."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from koschei.continuity_epoch_authority_v1 import bind_continuity_epoch_authority_v1
from koschei.mir import require_mir
from koschei.mir_go_native import generate_go_mir_native
from koschei.modules import check_graph, load_graph
from koschei.strange_representation_epoch_v1 import (
    StrangeRepresentationEpochError,
    derive_strange_epoch_seed_v1,
    project_strange_epoch_go_v1,
    require_strange_epoch_window_v1,
)


ROOT = Path(__file__).resolve().parents[1]
VEYRA = "b" * 64


class StrangeRepresentationEpochV1Tests(unittest.TestCase):
    def setUp(self):
        self.epoch = 9
        self.seconds = 500
        self.continuity = bind_continuity_epoch_authority_v1(
            continuity_id="test-continuity", epoch_reader=lambda: self.epoch
        )
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)

    def params(self):
        return dict(
            trust_plane_seed=b"k" * 32,
            continuity=self.continuity,
            expected_epoch=9,
            starts_at_seconds=500,
            seconds_reader=lambda: self.seconds,
            deployment_id="tenant-a/service-1",
            veyra_digest=VEYRA,
            mir_fingerprint=self.mir.fingerprint,
        )

    def test_119_seconds_pass_120_seconds_fail(self):
        self.seconds = 619
        self.assertEqual(
            require_strange_epoch_window_v1(
                continuity=self.continuity, expected_epoch=9,
                starts_at_seconds=500, seconds_reader=lambda: self.seconds,
            ),
            619,
        )
        self.seconds = 620
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**self.params())

    def test_future_window_and_epoch_drift_fail_closed(self):
        self.seconds = 499
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**self.params())
        self.seconds = 500
        self.epoch = 10
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**self.params())
        self.epoch = 8
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**self.params())

    def test_bad_clock_and_seed_fail_closed(self):
        p = self.params()
        p["seconds_reader"] = lambda: True
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**p)
        p["seconds_reader"] = lambda: (_ for _ in ()).throw(OSError("reader failed"))
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**p)
        p = self.params()
        p["trust_plane_seed"] = b"too-short"
        with self.assertRaises(StrangeRepresentationEpochError):
            derive_strange_epoch_seed_v1(**p)

    def test_noncanonical_digest_and_unrepresentable_epoch_fail_closed(self):
        for fingerprint in ("F" * 64, "ab " * 20 + "abab", "x" * 64):
            params = self.params()
            params["mir_fingerprint"] = fingerprint
            with self.subTest(fingerprint=fingerprint), self.assertRaises(StrangeRepresentationEpochError):
                derive_strange_epoch_seed_v1(**params)
        for epoch, start in ((2**64, 500), (9, 2**64)):
            params = self.params()
            params["expected_epoch"] = epoch
            params["starts_at_seconds"] = start
            with self.subTest(epoch=epoch, start=start), self.assertRaises(StrangeRepresentationEpochError):
                derive_strange_epoch_seed_v1(**params)

    def test_seed_is_scoped_by_epoch_customer_and_deployment(self):
        original = derive_strange_epoch_seed_v1(**self.params())
        self.assertEqual(original, derive_strange_epoch_seed_v1(**self.params()))
        changed = dict(self.params(), deployment_id="tenant-a/service-2")
        self.assertNotEqual(original, derive_strange_epoch_seed_v1(**changed))
        changed = dict(self.params(), veyra_digest="c" * 64)
        self.assertNotEqual(original, derive_strange_epoch_seed_v1(**changed))
        changed = dict(self.params(), mir_fingerprint="d" * 64)
        self.assertNotEqual(original, derive_strange_epoch_seed_v1(**changed))
        self.epoch = 10
        self.seconds = 620
        changed = dict(self.params(), expected_epoch=10, starts_at_seconds=620)
        self.assertNotEqual(original, derive_strange_epoch_seed_v1(**changed))

    def test_epoch_projection_matches_canonical_and_is_reproducible(self):
        p = self.params()
        p.pop("mir_fingerprint")
        source, receipt = project_strange_epoch_go_v1(self.mir, **p)
        again, second = project_strange_epoch_go_v1(self.mir, **p)
        self.assertEqual((source, receipt), (again, second))
        self.assertNotEqual(source, generate_go_mir_native(self.mir))
        self.assertIn("func _k_", source)
        self.assertEqual(receipt.expires_before_seconds, 620)
        self.assertEqual(receipt.source_sha256, hashlib.sha256(source.encode()).hexdigest())
        self.assertFalse(receipt.authority)
        self.seconds = 620
        with self.assertRaises(StrangeRepresentationEpochError):
            project_strange_epoch_go_v1(self.mir, **p)

    def test_time_race_at_projection_fails_closed(self):
        p = self.params()
        p.pop("mir_fingerprint")
        underlying = generate_go_mir_native

        def expire_window(mir, *, representation_seed=None):
            source = underlying(mir, representation_seed=representation_seed)
            self.seconds = 620
            return source

        with patch("koschei.strange_representation_epoch_v1.generate_go_mir_native", expire_window):
            with self.assertRaises(StrangeRepresentationEpochError):
                project_strange_epoch_go_v1(self.mir, **p)

    def test_epoch_race_at_projection_fails_closed(self):
        p = self.params()
        p.pop("mir_fingerprint")
        underlying = generate_go_mir_native

        def advance_epoch(mir, *, representation_seed=None):
            source = underlying(mir, representation_seed=representation_seed)
            self.epoch += 1
            return source

        with patch("koschei.strange_representation_epoch_v1.generate_go_mir_native", advance_epoch):
            with self.assertRaises(StrangeRepresentationEpochError):
                project_strange_epoch_go_v1(self.mir, **p)


if __name__ == "__main__":
    unittest.main()
