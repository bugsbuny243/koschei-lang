"""Linux+Go end-to-end integration for the Strange cutover coordinator.

Uses an actual pinned Go compiler and sealed memfd native worker; no
mocking of build, atomic handoff, durable launch claim or process execution.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph
from koschei.strange_cutover_orchestrator_v1 import (
    StrangeCutoverError,
    prepare_and_stage_next_epoch_v1,
    activate_and_reconcile_cutover_v1,
)
from koschei.strange_durable_continuity_v1 import StrangeDurableContinuityV1
from koschei.strange_durable_launch_reconciliation_v1 import (
    StrangeDurableLaunchReconciliationV1,
)
from koschei.strange_epoch_handoff_v1 import StrangeEpochHandoffV1

ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")
SUPPORTED = sys.platform == "linux" and GO is not None


@unittest.skipUnless(SUPPORTED, "Linux + pinned Go compiler required")
class StrangeCutoverOrchestratorIntegrationV1Tests(unittest.TestCase):
    def test_real_go_build_atomic_handoff_memfd_native_and_once_only_claim(self):
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)
        go = str(Path(GO).resolve())
        with Path(go).open("rb") as fp:
            go_sha256 = hashlib.file_digest(fp, "sha256").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            with StrangeDurableContinuityV1(
                Path(tmp) / "continuity.sqlite3", continuity_id="tenant-integration",
            ) as continuity:
                continuity.initialize(epoch=4, starts_at_seconds=480, observed_seconds=480)
                now = [599]
                clock = lambda: now[0]
                staged = prepare_and_stage_next_epoch_v1(
                    mir,
                    continuity_store=continuity,
                    trust_plane_seed=b"S" * 32,
                    expected_current_epoch=4,
                    expected_current_start_seconds=480,
                    seconds_reader=clock,
                    deployment_id="tenant-integration/worker",
                    veyra_digest="a" * 64,
                    go_executable=go,
                    expected_go_sha256=go_sha256,
                    handoff_key=b"H" * 32,
                    build_timeout_seconds=90,
                )
                self.assertEqual(staged.handoff.state, "STAGED")
                self.assertEqual(continuity.read_snapshot().epoch, 4)
                now[0] = 600
                params = dict(
                    continuity_store=continuity,
                    staged=staged,
                    handoff_key=b"H" * 32,
                    trust_plane_seed=b"S" * 32,
                    seconds_reader=clock,
                    deployment_id="tenant-integration/worker",
                    veyra_digest="a" * 64,
                    attestation_key=b"A" * 32,
                    expected_go_sha256=go_sha256,
                    run_timeout_seconds=5,
                    poll_interval_seconds=0.02,
                )
                observed = activate_and_reconcile_cutover_v1(mir, **params)
                self.assertEqual(observed.exit_code, 0)
                self.assertEqual(observed.stdout, b"Koschei\\n1\\n")
                self.assertFalse(observed.authority)
                self.assertEqual(observed.native_sha256, staged.pending.native_sha256)
                self.assertEqual(continuity.read_snapshot().epoch, 5)
                handoff = StrangeEpochHandoffV1(continuity)
                self.assertEqual(handoff.read(4).state, "ACTIVATED")
                self.assertTrue(handoff.retired(4))
                claim = StrangeDurableLaunchReconciliationV1(continuity).read(epoch=5)
                self.assertEqual(claim.state, "REPORTED_OK")
                with self.assertRaises(StrangeCutoverError):
                    activate_and_reconcile_cutover_v1(mir, **params)
                self.assertEqual(
                    StrangeDurableLaunchReconciliationV1(continuity).read(epoch=5).state,
                    "REPORTED_OK",
                )


if __name__ == "__main__":
    unittest.main()
