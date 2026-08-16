from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter
from koschei.mir import require_mir
from koschei.native_cell_reuse_composition_v1 import (
    NATIVE_CELL_REUSE_COMPOSITION_FRONTEND_V1,
    decode_native_cell_reuse_composition_graph,
    encode_native_cell_reuse_composition_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellReuseCompositionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("71" * 16)
        self.root_id = bytes.fromhex("72" * 16)
        self.cell_id = bytes.fromhex("73" * 16)
        self.reusable_id = bytes.fromhex("74" * 16)
        self.schema_id = bytes.fromhex("75" * 16)
        self.realization_id = bytes.fromhex("76" * 16)
        self.root_source = b"witness value conduit 0\nresolve value\n"
        self.cell_source = (
            b"witness amount 40\n"
            b"witness fee 2\n"
            b"witness approved truth yes\n"
            b"resolve approved\n"
            b"resolve fee\n"
            b"resolve amount\n"
        )
        self.reusable_source = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )
        self.objects = {
            self.root_id: self.root_source,
            self.cell_id: self.cell_source,
            self.reusable_id: self.reusable_source,
        }
        self.secret = encode_native_cell_reuse_composition_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            cell_object_id=self.cell_id,
            reusable_object_id=self.reusable_id,
            objects=self.objects,
            schema_id=self.schema_id,
            cell_witnesses=("amount", "fee", "approved"),
            input_cell_ordinals=(0, 1),
            root_slot=0,
            realization_id=self.realization_id,
            current_epoch=1,
            issued_epoch=1,
            expires_epoch=2,
        )

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def opener(self, root: Path, project, handle):
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

    def test_sealed_cell_projections_feed_reusable_business_reality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = self.opener(root, project, handle)
            checked = decode_native_cell_reuse_composition_graph(loaded)
            self.assertEqual(checked.schema_id, self.schema_id)
            self.assertEqual(checked.ordered_cell_witnesses, ("amount", "fee", "approved"))
            self.assertEqual(
                tuple((value.domain, value.value) for value in checked.cell_values),
                (("whole", 40), ("whole", 2), ("truth", True)),
            )
            self.assertEqual(checked.input_cell_ordinals, (0, 1))
            self.assertEqual(checked.reusable.value, 42)
            self.assertEqual(checked.root.value, 42)
            self.assertEqual(Interpreter(checked.root.lowered, []).execute_main(), 42)

    def test_three_source_objects_have_no_member_or_call_surface(self) -> None:
        joined = b"\n".join(self.objects.values()).decode("utf-8")
        for borrowed in (
            "field",
            "member",
            "index",
            "get",
            "call",
            "function",
            "parameter",
            ".",
            "[",
            "]",
            "{",
            "}",
            ":",
        ):
            self.assertNotIn(borrowed, joined)

    def test_installed_object_space_dispatch_runs_composed_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)

            def open_for_session(path: Path):
                return self.opener(path, project, handle)

            with object_space_check_session(open_for_session):
                _, graph = commands._checked(str(root))
                mir = require_mir(graph)
                mir.assert_sealed()
                runtime = Interpreter(
                    mir.root_module.program,
                    [],
                    mir.namespaces(),
                    dict(mir.root_module.imports),
                    mir.enums(),
                    mir.module_imports(),
                    mir.structs(),
                ).execute_main()
                self.assertEqual(runtime, 42)

    def test_composition_frontend_identity_is_nonzero(self) -> None:
        self.assertEqual(len(NATIVE_CELL_REUSE_COMPOSITION_FRONTEND_V1), 32)
        self.assertTrue(any(NATIVE_CELL_REUSE_COMPOSITION_FRONTEND_V1))


if __name__ == "__main__":
    unittest.main()
