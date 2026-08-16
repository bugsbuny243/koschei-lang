from __future__ import annotations

import unittest

from koschei.native_relationship_v1 import (
    NativeRelationshipSpecV1,
    encode_native_relationship_graph_secret,
)


class NativeRelationshipScaleV1Tests(unittest.TestCase):
    def test_2048_leaf_relationship_frontier_fits_full_root_witness_budget(self) -> None:
        leaf_count = 2048
        project_id = (0xD001).to_bytes(16, "big")
        root_id = (0xD002).to_bytes(16, "big")
        objects: dict[bytes, bytes] = {}
        relationships: list[NativeRelationshipSpecV1] = []
        lines: list[str] = []

        for index in range(leaf_count):
            target_id = (0x10000 + index).to_bytes(16, "big")
            relation_id = (0x20000 + index).to_bytes(16, "big")
            objects[target_id] = b"witness v 1\nresolve v\n"
            relationships.append(
                NativeRelationshipSpecV1(
                    relation_id=relation_id,
                    slot=index,
                    target_object_id=target_id,
                    issued_epoch=1,
                    expires_epoch=2,
                    max_target_witnesses=1,
                    max_abs_value=1,
                )
            )
            lines.append(f"witness c{index} conduit {index}")

        lines.append("witness a0 sum c0 c1")
        for index in range(2, leaf_count):
            lines.append(f"witness a{index - 1} sum a{index - 2} c{index}")
        lines.append(f"resolve a{leaf_count - 2}")
        objects[root_id] = ("\n".join(lines) + "\n").encode("ascii")

        secret = encode_native_relationship_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
            current_epoch=1,
            relationships=tuple(relationships),
        )
        self.assertGreater(len(secret), 400_000)
        self.assertEqual(len(objects), 2049)
        self.assertEqual(len(relationships), 2048)


if __name__ == "__main__":
    unittest.main()
