from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from koschei.native_reusable_realities_v1 import (
    NativeReusableRealizationSpecV1,
    decode_native_reusable_graph,
    encode_native_reusable_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeReusableRealitiesScaleV1Tests(unittest.TestCase):
    def test_2048_realizations_share_one_source_object_at_full_root_frontier(self) -> None:
        project_id = bytes.fromhex("e1" * 16)
        root_id = bytes.fromhex("e2" * 16)
        reusable_id = bytes.fromhex("e3" * 16)
        reusable_source = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )

        root_lines = [f"witness c{index} conduit {index}" for index in range(2048)]
        root_lines.append("witness s0 sum c0 c1")
        for index in range(1, 2047):
            root_lines.append(f"witness s{index} sum s{index - 1} c{index + 1}")
        root_lines.append("resolve s2046")
        root_source = ("\n".join(root_lines) + "\n").encode("ascii")

        realizations = tuple(
            NativeReusableRealizationSpecV1(
                realization_id=index.to_bytes(16, "big"),
                root_slot=index,
                reusable_object_id=reusable_id,
                inputs=(1, 1),
                issued_epoch=1,
                expires_epoch=2,
                max_abs_input=1,
                max_abs_output=2,
                max_reusable_witnesses=3,
            )
            for index in range(1, 2049)
        )
        # IDs must be non-zero, while root slots are 0-based.
        realizations = tuple(
            replace(item, root_slot=index)
            for index, item in enumerate(realizations)
        )
        objects = {root_id: root_source, reusable_id: reusable_source}
        secret = encode_native_reusable_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
            current_epoch=1,
            realizations=realizations,
        )
        self.assertGreater(len(secret), 300_000)
        self.assertLess(len(secret), 4 << 20)

        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = create_object_space_project(
                Path(temporary) / "space",
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
                root_object_id=root_id,
                graph_secret=secret,
                temporal_policy=policy,
                now=1_800_000_000,
                project_id=project_id,
            )
            checked = decode_native_reusable_graph(project)
            self.assertEqual(len(project.object_payloads), 2)
            self.assertEqual(len(checked.reusable_objects), 1)
            self.assertEqual(len(checked.realizations), 2048)
            self.assertEqual(len(checked.root.kernel.witnesses), 4095)
            self.assertEqual(checked.root.value, 4096)
            self.assertEqual(
                {record.reusable_object_id for record in checked.realizations},
                {reusable_id},
            )


if __name__ == "__main__":
    unittest.main()
