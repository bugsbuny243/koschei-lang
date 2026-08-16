from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.interpreter import Interpreter
from koschei.mir import require_mir
from koschei.native_cell_projection_v1 import (
    NATIVE_CELL_PROJECTION_FRONTEND_V1,
    decode_native_cell_projection_graph,
    encode_native_cell_projection_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellProjectionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("e1" * 16)
        self.root_id = bytes.fromhex("e2" * 16)
        self.schema_id = bytes.fromhex("e3" * 16)
        self.names = ("total", "approved", "label")
        self.source = (
            b"witness amount 40\n"
            b"witness fee 2\n"
            b"witness total sum amount fee\n"
            b"witness approved truth yes\n"
            b"witness label glyphs 4 paid\n"
            b"resolve label\n"
            b"resolve total\n"
            b"resolve approved\n"
        )

    def secret(self, selected: int, source: bytes | None = None) -> bytes:
        payload = self.source if source is None else source
        return encode_native_cell_projection_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects={self.root_id: payload},
            schema_id=self.schema_id,
            cell_witnesses=self.names,
            selected_ordinal=selected,
        )

    def create(self, root: Path, selected: int):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects={self.root_id: self.source},
            root_object_id=self.root_id,
            graph_secret=self.secret(selected),
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

    def test_projection_returns_each_scalar_domain_without_member_syntax(self) -> None:
        expected = ((0, "whole", 42), (1, "truth", True), (2, "glyphs", "paid"))
        for ordinal, domain, value in expected:
            with self.subTest(ordinal=ordinal), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "space"
                project, handle = self.create(root, ordinal)
                loaded = self.opener(root, project, handle)
                checked = decode_native_cell_projection_graph(loaded)
                self.assertEqual(checked.selected_ordinal, ordinal)
                self.assertEqual(checked.selected_value.domain, domain)
                self.assertEqual(checked.selected_value.value, value)
                self.assertEqual(Interpreter(checked.lowered, []).execute_main(), value)

    def test_source_contains_no_projection_or_mainstream_access_surface(self) -> None:
        source = self.source.decode("utf-8")
        for borrowed in (
            "field",
            "member",
            "index",
            "get",
            "struct",
            "record",
            "tuple",
            "list",
            "map",
            ".",
            "[",
            "]",
            "{",
            "}",
            ":",
        ):
            self.assertNotIn(borrowed, source)

    def test_source_and_resolve_order_do_not_define_selected_ordinal(self) -> None:
        permuted = (
            b"resolve approved\n"
            b"witness label glyphs 4 paid\n"
            b"witness approved truth yes\n"
            b"resolve label\n"
            b"witness fee 2\n"
            b"witness total sum amount fee\n"
            b"resolve total\n"
            b"witness amount 40\n"
        )
        secret = self.secret(0, permuted)
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
            checked = decode_native_cell_projection_graph(loaded)
            self.assertEqual(checked.ordered_witnesses, self.names)
            self.assertEqual(checked.selected_value.value, 42)

    def test_installed_object_space_dispatch_executes_selected_scalar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root, 2)

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
                self.assertEqual(runtime, "paid")

    def test_projection_frontend_identity_is_distinct_and_nonzero(self) -> None:
        self.assertEqual(len(NATIVE_CELL_PROJECTION_FRONTEND_V1), 32)
        self.assertTrue(any(NATIVE_CELL_PROJECTION_FRONTEND_V1))


if __name__ == "__main__":
    unittest.main()
