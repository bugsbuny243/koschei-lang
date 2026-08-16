from __future__ import annotations

import unittest

from koschei.temporal_access_v1 import (
    TemporalAccessError,
    TemporalAccessPolicy,
    _reset_process_highwater_for_tests,
    issue_temporal_handle,
    verify_temporal_handle,
)


class TemporalAccessRollbackV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = bytes(range(1, 65))
        self.project = bytes.fromhex("77" * 16)
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.t0 = 1_800_000_000
        _reset_process_highwater_for_tests(self.project)

    def tearDown(self) -> None:
        _reset_process_highwater_for_tests(self.project)

    def test_old_handle_does_not_revive_when_wall_clock_rolls_back(self) -> None:
        old = issue_temporal_handle(
            temporal_key=self.key,
            project_id=self.project,
            epoch=1,
            now=self.t0,
            policy=self.policy,
        )
        newer = issue_temporal_handle(
            temporal_key=self.key,
            project_id=self.project,
            epoch=1,
            now=self.t0 + 60,
            policy=self.policy,
        )
        verify_temporal_handle(
            newer,
            temporal_key=self.key,
            project_id=self.project,
            epoch=1,
            now=self.t0 + 60,
            policy=self.policy,
        )

        with self.assertRaisesRegex(TemporalAccessError, "rolled back"):
            verify_temporal_handle(
                old,
                temporal_key=self.key,
                project_id=self.project,
                epoch=1,
                now=self.t0,
                policy=self.policy,
            )

    def test_forged_future_handle_cannot_advance_highwater_and_dos_current_slot(self) -> None:
        current = issue_temporal_handle(
            temporal_key=self.key,
            project_id=self.project,
            epoch=1,
            now=self.t0,
            policy=self.policy,
        )
        forged = bytes([0xA5]) * 64
        with self.assertRaises(TemporalAccessError):
            verify_temporal_handle(
                forged,
                temporal_key=self.key,
                project_id=self.project,
                epoch=1,
                now=self.t0 + 600,
                policy=self.policy,
            )

        # A failed future probe must not pin the project high-water in the future.
        verify_temporal_handle(
            current,
            temporal_key=self.key,
            project_id=self.project,
            epoch=1,
            now=self.t0,
            policy=self.policy,
        )


if __name__ == "__main__":
    unittest.main()
