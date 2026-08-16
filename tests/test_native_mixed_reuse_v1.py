from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter
from koschei.native_mixed_reuse_v1 import (
    NativeMixedReuseError,
    decode_native_mixed_reuse_graph,
    encode_native_mixed_reuse_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeMixedReuseV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("81" * 16)
        self.root_id = bytes.fromhex("82" * 16)
        self.cell_id = bytes.fromhex("83" * 16)
        self.reusable_id = bytes.fromhex("84" * 16)
        self.schema_id = bytes.fromhex("85" * 16)
        self.realization_id = bytes.fromhex("86" * 16)
        self.root_source = b"witness result conduit 0\nresolve result\n"
        self.cell_source = (
            b"witness amount 40\n"
            b"witness approved truth yes\n"
            b"witness label glyphs 2 ok\n"
            b"resolve label\n"
            b"resolve amount\n"
            b"resolve approved\n"
        )
        self.reusable_source = (
            b"witness amount conduit 0\n"
            b"witness approved conduit 1\n"
            b"witness label conduit 2\n"
            b"witness amountok same amount 40\n"
            b"witness expected glyphs 2 ok\n"
            b"witness labelok same label expected\n"
            b"witness approvalok same approved amountok\n"
            b"witness result same approvalok labelok\n"
            b"resolve result\n"
        )
        self.objects = {
            self.root_id: self.root_source,
            self.cell_id: self.cell_source,
            self.reusable_id: self.reusable_source,
        }

    def secret(self, *, expected_output_domain: str = "truth") -> bytes:
        return encode_native_mixed_reuse_graph_secret(
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
            expected_output_domain=expected_output_domain,
            current_epoch=1,
            issued_epoch=1,
            expires_epoch=2,
        )

    def open_project(self, root: Path, secret: bytes):
        project, handle = create_object_space_project(
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

    def test_whole_truth_and_glyphs_feed_one_reusable_reality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            loaded = self.open_project(Path(temporary) / "space", self.secret())
            checked = decode_native_mixed_reuse_graph(loaded)
            self.assertEqual(checked.input_domains, ("whole", "truth", "glyphs"))
            self.assertEqual(checked.reusable.value.domain, "truth")
            self.assertIs(checked.reusable.value.value, True)
            self.assertEqual(checked.root.value.domain, "truth")
            self.assertIs(checked.root.value.value, True)
            self.assertIs(Interpreter(checked.root.lowered, []).execute_main(), True)

    def test_glyphs_result_can_cross_reusable_to_root(self) -> None:
        self.cell_source = (
            b"witness left glyphs 3 pay\n"
            b"witness right glyphs 2 ed\n"
            b"resolve right\n"
            b"resolve left\n"
        )
        self.reusable_source = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness result merge left right\n"
            b"resolve result\n"
        )
        self.objects = {
            self.root_id: self.root_source,
            self.cell_id: self.cell_source,
            self.reusable_id: self.reusable_source,
        }
        secret = encode_native_mixed_reuse_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            cell_object_id=self.cell_id,
            reusable_object_id=self.reusable_id,
            objects=self.objects,
            schema_id=self.schema_id,
            cell_witnesses=("left", "right"),
            input_cell_ordinals=(0, 1),
            root_slot=0,
            realization_id=self.realization_id,
            expected_output_domain="glyphs",
            current_epoch=1,
            issued_epoch=1,
            expires_epoch=2,
        )
        with tempfile.TemporaryDirectory() as temporary:
            loaded = self.open_project(Path(temporary) / "space", secret)
            checked = decode_native_mixed_reuse_graph(loaded)
            self.assertEqual(checked.reusable.value.value, "payed")
            self.assertEqual(checked.root.value.value, "payed")
            self.assertEqual(Interpreter(checked.root.lowered, []).execute_main(), "payed")

    def test_output_domain_is_sealed_not_inferred_at_load(self) -> None:
        with self.assertRaises(NativeMixedReuseError):
            self.secret(expected_output_domain="glyphs")

    def test_glyph_input_budget_fails_closed(self) -> None:
        with self.assertRaises(NativeMixedReuseError):
            encode_native_mixed_reuse_graph_secret(
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
                max_glyph_input_bytes=1,
            )


if __name__ == "__main__":
    unittest.main()
