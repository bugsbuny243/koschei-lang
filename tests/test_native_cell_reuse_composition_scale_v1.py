from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter
from koschei.native_cell_reuse_composition_v1 import (
    decode_native_cell_reuse_composition_graph,
    encode_native_cell_reuse_composition_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


def full_cell_source() -> tuple[bytes, tuple[str, ...]]:
    lines = ["witness w0 0"]
    for index in range(1, 4096):
        lines.append(f"witness w{index} sum w{index - 1} 0")
    names = tuple(f"w{index}" for index in range(4096 - 64, 4096))
    lines.extend(f"resolve {name}" for name in reversed(names))
    return ("\n".join(lines) + "\n").encode("utf-8"), names


class NativeCellReuseCompositionScaleV1Tests(unittest.TestCase):
    def test_full_4096_witness_cell_reality_feeds_reusable_without_source_copy(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("61" * 16)
        root_id = bytes.fromhex("62" * 16)
        cell_id = bytes.fromhex("63" * 16)
        reusable_id = bytes.fromhex("64" * 16)
        schema_id = bytes.fromhex("65" * 16)
        realization_id = bytes.fromhex("66" * 16)
        root_source = b"witness value conduit 0\nresolve value\n"
        cell_source, names = full_cell_source()
        reusable_source = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )
        objects = {
            root_id: root_source,
            cell_id: cell_source,
            reusable_id: reusable_source,
        }
        secret = encode_native_cell_reuse_composition_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            cell_object_id=cell_id,
            reusable_object_id=reusable_id,
            objects=objects,
            schema_id=schema_id,
            cell_witnesses=names,
            input_cell_ordinals=(62, 63),
            root_slot=0,
            realization_id=realization_id,
            current_epoch=1,
            issued_epoch=1,
            expires_epoch=2,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = create_object_space_project(
                root,
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
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
            checked = decode_native_cell_reuse_composition_graph(loaded)
            self.assertEqual(len(checked.cell_values), 64)
            self.assertEqual(checked.input_cell_ordinals, (62, 63))
            self.assertEqual(checked.reusable.value, 0)
            self.assertEqual(checked.root.value, 0)
            self.assertEqual(Interpreter(checked.root.lowered, []).execute_main(), 0)


if __name__ == "__main__":
    unittest.main()
