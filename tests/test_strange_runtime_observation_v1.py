"""Integration tests: runtime observation spans native evidence and durable epoch."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_native_admission_v1 import (
    issue_strange_native_attestation_v1,
    verify_strange_native_admission_v1,
)
from koschei.strange_representation_epoch_v1 import project_strange_epoch_go_v1
from koschei.strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    consume_strange_runtime_observation_once_v1,
    require_strange_runtime_observation_v1,
)


ROOT = Path(__file__).resolve().parents[1]


class StrangeRuntimeObservationV1Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = StrangeDurableContinuityV1(
            Path(self.directory.name) / "continuity.sqlite3",
            continuity_id="galaxy-a",
        )
        self.addCleanup(self.store.close)
        self.now = 480
        self.store.initialize(
            epoch=4, starts_at_seconds=480, observed_seconds=self.now,
        )
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        self.mir = require_mir(graph)
        self.native = b"native-executable-bytes"
        self.attestation_key = b"A" * 32
        _, self.projection = project_strange_epoch_go_v1(
            self.mir,
            trust_plane_seed=b"K" * 32,
            continuity=self.store.as_continuity_authority(),
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            deployment_id="galaxy-a/deploy-1",
            veyra_digest="a" * 64,
        )
        self.claim = dict(
            deployment_id="galaxy-a/deploy-1",
            veyra_digest="a" * 64,
            mir_fingerprint=self.mir.fingerprint,
            expected_epoch=4,
            expected_start_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=self.attestation_key,
        )
        self.proof = issue_strange_native_attestation_v1(
            receipt=self.projection,
            native_binary=self.native,
            deployment_id=self.claim["deployment_id"],
            veyra_digest=self.claim["veyra_digest"],
            mir_fingerprint=self.claim["mir_fingerprint"],
            continuity=self.store.as_continuity_authority(),
            expected_epoch=4,
            starts_at_seconds=480,
            seconds_reader=lambda: self.now,
            attestation_key=self.attestation_key,
        )

    def check(self, *, native=None, proof=None, **changes):
        params = dict(self.claim)
        params.update(changes)
        return require_strange_runtime_observation_v1(
            continuity_store=self.store,
            native_binary=self.native if native is None else native,
            attestation=self.proof if proof is None else proof,
            expected_source_sha256=self.projection.source_sha256,
            **params,
        )

    def consume(self, *, request_digest: str = "1" * 64, **changes):
        params = dict(self.claim)
        params.update(changes)
        return consume_strange_runtime_observation_once_v1(
            continuity_store=self.store,
            native_binary=self.native,
            attestation=self.proof,
            expected_source_sha256=self.projection.source_sha256,
            request_digest=request_digest,
            **params,
        )

    def test_single_use_observation_replay_denied(self):
        record = self.consume()
        self.assertEqual(record.request_digest, "1" * 64)
        self.assertEqual(record.epoch, 4)
        self.assertFalse(record.authority)
        with self.assertRaises(StrangeRuntimeObservationError):
            self.consume()
        self.assertEqual(self.consume(request_digest="2" * 64).epoch, 4)

    def test_duplicate_observation_rejected_across_database_connections(self):
        first = self.consume(request_digest="3" * 64)
        with StrangeDurableContinuityV1(
            Path(self.directory.name) / "continuity.sqlite3",
            continuity_id="galaxy-a",
        ) as reopened:
            with self.assertRaisesRegex(Exception, "already claimed"):
                reopened.claim_observation_once(
                    request_digest=first.request_digest,
                    attestation_digest=first.attestation_digest,
                    expected_epoch=4,
                    expected_start_seconds=480,
                    seconds_reader=lambda: 480,
                )

    def test_two_simultaneous_local_observation_claims_allow_exactly_one(self):
        def attempt():
            try:
                self.consume(request_digest="4" * 64)
                return "recorded"
            except StrangeRuntimeObservationError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt(), (1, 2)))
        self.assertEqual(sorted(results), ["recorded", "rejected"])

    def test_old_request_digest_cannot_be_reused_in_new_epoch(self):
        previous = self.consume(request_digest="9" * 64)
        self.store.advance(
            expected_current_epoch=4, next_epoch=5,
            starts_at_seconds=600, observed_seconds=600,
        )
        with self.assertRaisesRegex(Exception, "already claimed"):
            self.store.claim_observation_once(
                request_digest=previous.request_digest,
                attestation_digest=previous.attestation_digest,
                expected_epoch=5,
                expected_start_seconds=600,
                seconds_reader=lambda: 600,
            )

    def test_epoch_advances_after_verification_but_before_claim(self):
        original = self.store.claim_observation_once

        def rotate_before_claim(**arguments):
            self.store.advance(
                expected_current_epoch=4, next_epoch=5,
                starts_at_seconds=600, observed_seconds=600,
            )
            return original(**arguments)

        with patch.object(self.store, "claim_observation_once", side_effect=rotate_before_claim):
            with self.assertRaises(StrangeRuntimeObservationError):
                self.consume(request_digest="5" * 64)

    def test_window_expires_after_verification_but_before_claim(self):
        original = self.store.claim_observation_once

        def expire_before_claim(**arguments):
            self.now = 600
            return original(**arguments)

        with patch.object(self.store, "claim_observation_once", side_effect=expire_before_claim):
            with self.assertRaises(StrangeRuntimeObservationError):
                self.consume(request_digest="6" * 64)

    def test_invalid_digest_and_rejected_binary_never_create_claim(self):
        with self.assertRaises(StrangeRuntimeObservationError):
            self.consume(request_digest="invalid")
        with self.assertRaises(StrangeRuntimeObservationError):
            consume_strange_runtime_observation_once_v1(
                continuity_store=self.store,
                native_binary=b"tampered-native",
                attestation=self.proof,
                expected_source_sha256=self.projection.source_sha256,
                request_digest="7" * 64,
                **self.claim,
            )
        self.assertEqual(self.consume(request_digest="7" * 64).epoch, 4)

    def test_current_native_artifact_is_observed_without_authority(self):
        observed = self.check()
        self.assertFalse(observed.authority)
        self.assertEqual((observed.observed_epoch, observed.expires_before_seconds), (4, 600))

    def test_modified_artifact_and_forged_evidence_fail_closed(self):
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(native=b"modified-native")
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(proof=replace(self.proof, attestation_mac="f" * 64))
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(deployment_id="galaxy-b/deploy-1")
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(veyra_digest="b" * 64)

    def test_window_expiry_and_stale_epoch_fail_closed(self):
        self.now = 599
        self.check()
        self.now = 600
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check()
        self.store.advance(
            expected_current_epoch=4,
            next_epoch=5,
            starts_at_seconds=600,
            observed_seconds=600,
        )
        self.now = 599
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check()

    def test_substituted_start_and_invalid_clock_fail_closed(self):
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(expected_start_seconds=481)
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(seconds_reader=lambda: True)
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(seconds_reader=lambda: (_ for _ in ()).throw(OSError("clock missing")))

    def test_epoch_rotation_during_native_verification_fails_closed(self):
        real_verify = verify_strange_native_admission_v1

        def verify_and_rotate(**arguments):
            real_verify(**arguments)
            self.store.advance(
                expected_current_epoch=4,
                next_epoch=5,
                starts_at_seconds=600,
                observed_seconds=600,
            )

        with patch(
            "koschei.strange_runtime_observation_v1.verify_strange_native_admission_v1",
            side_effect=verify_and_rotate,
        ):
            with self.assertRaises(StrangeRuntimeObservationError):
                self.check()

    def test_window_expiry_during_native_verification_fails_closed(self):
        real_verify = verify_strange_native_admission_v1

        def verify_then_expire(**arguments):
            real_verify(**arguments)
            self.now = 600

        with patch(
            "koschei.strange_runtime_observation_v1.verify_strange_native_admission_v1",
            side_effect=verify_then_expire,
        ):
            with self.assertRaises(StrangeRuntimeObservationError):
                self.check()

    def test_backward_clock_during_verification_fails_closed(self):
        values = iter((480, 480, 479, 480))
        with self.assertRaises(StrangeRuntimeObservationError):
            self.check(seconds_reader=lambda: next(values))

    def test_restarted_local_ledger_keeps_current_epoch(self):
        self.store.close()
        # Dispose original and suppress double-close from cleanup by creating
        # a new local instance only for the restart verification.
        with StrangeDurableContinuityV1(
            Path(self.directory.name) / "continuity.sqlite3", continuity_id="galaxy-a"
        ) as reopened:
            self.assertEqual(reopened.read_snapshot().epoch, 4)
            # The same native proof remains valid only inside its epoch.
            observed = require_strange_runtime_observation_v1(
                continuity_store=reopened,
                native_binary=self.native,
                attestation=self.proof,
                expected_source_sha256=self.projection.source_sha256,
                **self.claim,
            )
            self.assertFalse(observed.authority)


if __name__ == "__main__":
    unittest.main()
