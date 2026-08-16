from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter, StructValue
from koschei.native_cell_realities_v1 import (
    MAX_CELL_COUNT_V1,
    NativeCellRealityError,
    decode_native_cell_graph,
    encode_native_cell_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellRealitiesScaleV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("d1" * 16)
        self.root_id = bytes.fromhex("d2" * 16)
        self.schema_id = bytes.fromhex("d3" * 16)

    @staticmethod
    def full_frontier_source(cell_count: int = MAX_CELL_COUNT_V1) -> tuple[bytes, tuple[str, ...]]:
        lines = ["witness w0 0"]
        for index in range(1, 4096):
            lines.append(f"witness w{index} sum w{index - 1} 0")
        names = tuple(f"w{index}" for index in range(4096 - cell_count, 4096))
        # Resolve clause order is deliberately reversed relative to schema order.
        lines.extend(f"resolve {name}" for name in reversed(names))
        return ("\n".join(lines) + "\n").encode("utf-8"), names

    def test_64_cells_share_full_4096_witness_dependency_reality(self) -> None:
        source, names = self.full_frontier_source()
        secret = encode_native_cell_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects={self.root_id: source},
            schema_id=self.schema_id,
            cell_witnesses=names,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = create_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                objects={self.root_id: source},
                root_object_id=self.root_id,
                graph_secret=secret,
                temporal_policy=self.policy,
                now=self.now,
                project_id=self.project_id,
            )
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            checked = decode_native_cell_graph(loaded)
            self.assertEqual(len(checked.dependency_order), 4096)
            self.assertEqual(len(checked.cells), 64)
            self.assertEqual(checked.ordered_witnesses, names)
            self.assertTrue(all(cell.value == 0 for cell in checked.cells))
            runtime = Interpreter(checked.lowered, []).execute_main()
            self.assertIsInstance(runtime, StructValue)
            self.assertEqual(len(runtime.fields), 64)
            self.assertEqual(runtime.fields["c0"], 0)
            self.assertEqual(runtime.fields["c63"], 0)

    def test_65th_cell_is_rejected_at_language_boundary(self) -> None:
        lines = [f"witness w{index} {index}" for index in range(65)]
        lines.extend(f"resolve w{index}" for index in range(65))
        source = ("\n".join(lines) + "\n").encode("utf-8")
        with self.assertRaisesRegex(NativeCellRealityError, "64"):
            encode_native_cell_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects={self.root_id: source},
                schema_id=self.schema_id,
                cell_witnesses=tuple(f"w{index}" for index in range(65)),
            )


if __name__ == "__main__":
    unittest.main()
