from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter
from koschei.native_cell_projection_v1 import (
    decode_native_cell_projection_graph,
    encode_native_cell_projection_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


def full_frontier_source() -> tuple[bytes, tuple[str, ...]]:
    lines = ["witness w0 0"]
    for index in range(1, 4096):
        lines.append(f"witness w{index} sum w{index - 1} 0")
    names = tuple(f"w{index}" for index in range(4096 - 64, 4096))
    lines.extend(f"resolve {name}" for name in reversed(names))
    return ("\n".join(lines) + "\n").encode("utf-8"), names


class NativeCellProjectionScaleV1Tests(unittest.TestCase):
    def test_projection_validates_full_4096_witness_64_cell_reality(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("91" * 16)
        root_id = bytes.fromhex("92" * 16)
        schema_id = bytes.fromhex("93" * 16)
        source, names = full_frontier_source()
        secret = encode_native_cell_projection_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects={root_id: source},
            schema_id=schema_id,
            cell_witnesses=names,
            selected_ordinal=63,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = create_object_space_project(
                root,
                provider=provider,
                temporal_key=temporal_key,
                objects={root_id: source},
                root_object_id=root_id,
                graph_secret=secret,
                temporal_policy=policy,
                now=now,
                project_id=project_id,
            )
            loaded = load_object_space_project(
                root,
                provider=provider,
                temporal_key=temporal_key,
                temporal_handle=handle,
                expected_project_id=project_id,
                expected_epoch=1,
                temporal_policy=policy,
                now=now,
            )
            checked = decode_native_cell_projection_graph(loaded)
            self.assertEqual(len(checked.dependency_order), 4096)
            self.assertEqual(len(checked.cells), 64)
            self.assertEqual(checked.selected_ordinal, 63)
            self.assertEqual(checked.ordered_witnesses, names)
            self.assertEqual(checked.selected_value.value, 0)
            self.assertEqual(Interpreter(checked.lowered, []).execute_main(), 0)


if __name__ == "__main__":
    unittest.main()
