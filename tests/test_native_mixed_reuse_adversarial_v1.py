from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.native_cell_realities_v1 import _CELL, _DOMAIN_TO_CODE
from koschei.native_mixed_reuse_v1 import (
    NativeMixedReuseError,
    _BINDING,
    _HEADER,
    _OBJECT,
    decode_native_mixed_reuse_graph,
    encode_native_mixed_reuse_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeMixedReuseAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("91" * 16)
        self.root_id = bytes.fromhex("92" * 16)
        self.cell_id = bytes.fromhex("93" * 16)
        self.reusable_id = bytes.fromhex("94" * 16)
        self.schema_id = bytes.fromhex("95" * 16)
        self.realization_id = bytes.fromhex("96" * 16)
        self.objects = {
            self.root_id: b"witness result conduit 0\nresolve result\n",
            self.cell_id: (
                b"witness amount 40\n"
                b"witness approved truth yes\n"
                b"witness label glyphs 2 ok\n"
                b"resolve label\n"
                b"resolve amount\n"
                b"resolve approved\n"
            ),
            self.reusable_id: (
                b"witness amount conduit 0\n"
                b"witness approved conduit 1\n"
                b"witness label conduit 2\n"
                b"witness amountok same amount 40\n"
                b"witness expected glyphs 2 ok\n"
                b"witness labelok same label expected\n"
                b"witness approvalok same approved amountok\n"
                b"witness result same approvalok labelok\n"
                b"resolve result\n"
            ),
        }
        self.secret = encode_native_mixed_reuse_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            cell_object_id=self.cell_id,
            reusable_object_id=self.reusable_id,
            objects=self.objects,
            schema_id=self.schema_id,
            cell_witnesses=("amount", "approved", "label"),
            input_cell_ordinals=(0, 1, 2),
            root_slot=0,
            realization_id=self.realization_id,
            expected_output_domain="truth",
            current_epoch=1,
            issued_epoch=1,
            expires_epoch=2,
        )

    def loaded(self, secret: bytes):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "space"
        _, handle = create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )
        return load_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=self.project_id,
            expected_epoch=1,
            temporal_policy=self.policy,
            now=self.now,
        )

    def test_binding_domain_tamper_fails_closed_at_load(self) -> None:
        payload = bytearray(self.secret)
        binding_offset = _HEADER.size + 3 * _OBJECT.size + 3 * _CELL.size
        payload[binding_offset + 4] = _DOMAIN_TO_CODE["truth"]
        with self.assertRaises(NativeMixedReuseError):
            decode_native_mixed_reuse_graph(self.loaded(bytes(payload)))

    def test_output_domain_header_tamper_fails_closed_at_load(self) -> None:
        payload = bytearray(self.secret)
        payload[_HEADER.size - 8] = _DOMAIN_TO_CODE["glyphs"]
        with self.assertRaises(NativeMixedReuseError):
            decode_native_mixed_reuse_graph(self.loaded(bytes(payload)))

    def test_authority_inflation_fails_before_materialization(self) -> None:
        fields = list(_HEADER.unpack_from(self.secret, 0))
        fields[16] = 1
        tampered = _HEADER.pack(*fields) + self.secret[_HEADER.size :]
        with self.assertRaises(NativeMixedReuseError):
            decode_native_mixed_reuse_graph(self.loaded(tampered))


if __name__ == "__main__":
    unittest.main()
