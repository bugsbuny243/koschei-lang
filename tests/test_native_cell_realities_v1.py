from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter, StructValue
from koschei.mir import require_mir
from koschei.native_cell_realities_v1 import (
    NATIVE_CELL_FRONTEND_V1,
    decode_native_cell_graph,
    encode_native_cell_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellRealitiesV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("a1" * 16)
        self.root_id = bytes.fromhex("a2" * 16)
        self.schema_id = bytes.fromhex("a3" * 16)
        self.source = (
            "witness amount 40\n"
            "witness fee 2\n"
            "witness total sum amount fee\n"
            "witness approved truth yes\n"
            "witness label glyphs 4 paid\n"
            "resolve label\n"
            "resolve total\n"
            "resolve approved\n"
        ).encode("utf-8")

    def build_secret(self, source: bytes | None = None):
        payload = self.source if source is None else source
        return encode_native_cell_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects={self.root_id: payload},
            schema_id=self.schema_id,
            cell_witnesses=("total", "approved", "label"),
        )

    def create(self, root: Path):
        secret = self.build_secret()
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects={self.root_id: self.source},
            root_object_id=self.root_id,
            graph_secret=secret,
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
            expected_project_id=project.project_id,
            expected_epoch=1,
            temporal_policy=self.policy,
            now=self.now,
        )

    def test_mixed_scalar_cells_form_one_schema_bound_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = self.opener(root, project, handle)
            checked = decode_native_cell_graph(loaded)

            self.assertEqual(checked.schema_id, self.schema_id)
            self.assertEqual(checked.ordered_witnesses, ("total", "approved", "label"))
            self.assertEqual(
                tuple((cell.domain, cell.value) for cell in checked.cells),
                (("whole", 42), ("truth", True), ("glyphs", "paid")),
            )
            runtime = Interpreter(checked.lowered, []).execute_main()
            self.assertIsInstance(runtime, StructValue)
            self.assertEqual(runtime.type_name, "KCellReality")
            self.assertEqual(runtime.fields, {"c0": 42, "c1": True, "c2": "paid"})

    def test_source_has_no_mainstream_aggregate_surface(self) -> None:
        source = self.source.decode("utf-8")
        for borrowed in (
            "struct",
            "record",
            "tuple",
            "list",
            "map",
            "class",
            "field",
            "{",
            "}",
            "[",
            "]",
            ":",
        ):
            self.assertNotIn(borrowed, source)

    def test_resolve_clause_order_is_not_schema_cell_order(self) -> None:
        permuted = (
            "resolve approved\n"
            "witness label glyphs 4 paid\n"
            "witness approved truth yes\n"
            "resolve label\n"
            "witness fee 2\n"
            "witness total sum amount fee\n"
            "resolve total\n"
            "witness amount 40\n"
        ).encode("utf-8")
        secret = self.build_secret(permuted)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = create_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                objects={self.root_id: permuted},
                root_object_id=self.root_id,
                graph_secret=secret,
                temporal_policy=self.policy,
                now=self.now,
                project_id=self.project_id,
            )
            loaded = self.opener(root, project, handle)
            checked = decode_native_cell_graph(loaded)
            self.assertEqual(
                tuple(cell.value for cell in checked.cells),
                (42, True, "paid"),
            )

    def test_installed_object_space_dispatch_reaches_native_cell_frontend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)

            def open_for_session(path: Path):
                return self.opener(path, project, handle)

            with object_space_check_session(open_for_session):
                _, graph = commands._checked(str(root))
                mir_graph = require_mir(graph)
                mir_graph.assert_sealed()
                runtime = Interpreter(
                    mir_graph.root_module.program,
                    [],
                    mir_graph.namespaces(),
                    dict(mir_graph.root_module.imports),
                    mir_graph.enums(),
                    mir_graph.module_imports(),
                    mir_graph.structs(),
                ).execute_main()
                self.assertIsInstance(runtime, StructValue)
                self.assertEqual(runtime.fields["c0"], 42)
                self.assertEqual(runtime.fields["c1"], True)
                self.assertEqual(runtime.fields["c2"], "paid")

    def test_frontend_identity_is_distinct_and_nonzero(self) -> None:
        self.assertEqual(len(NATIVE_CELL_FRONTEND_V1), 32)
        self.assertTrue(any(NATIVE_CELL_FRONTEND_V1))


if __name__ == "__main__":
    unittest.main()
