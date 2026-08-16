from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei import cli
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    check_authenticated_frontend_graph,
    check_object_space_graph_by_authenticated_frontend,
    decode_authenticated_frontend_graph,
    encode_authenticated_frontend_graph_secret,
    load_authenticated_native_kernel,
)
from koschei.object_space_graph_v1 import encode_object_space_graph_secret
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class AuthenticatedFrontendIdentityV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("61" * 16)
        self.root_id = bytes.fromhex("72" * 16)
        self.native_source = (
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n"
        )
        self.objects = {self.root_id: self.native_source}
        self.graph_secret = encode_authenticated_frontend_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
        )

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.graph_secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def opener(self, handle: bytes):
        def open_project(root: Path):
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

        return open_project

    def test_round_trip_binds_root_object_to_native_frontend_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "reality")
            records = decode_authenticated_frontend_graph(project)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].object_id, self.root_id)
            self.assertEqual(records[0].frontend_id, NATIVE_WITNESS_FRONTEND_V1)
            checked = load_authenticated_native_kernel(project)
            self.assertEqual(checked.value, 42)

    def test_native_metadata_path_never_calls_legacy_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "reality")
            with patch(
                "koschei.object_space_graph_v1.parse",
                side_effect=AssertionError("legacy parser reached"),
            ):
                graph, report = check_object_space_graph_by_authenticated_frontend(project)
            self.assertEqual(graph.root, self.root_id.hex())
            self.assertEqual(len(graph.modules), 1)
            self.assertEqual(report.functions, 1)
            self.assertIsNotNone(graph.mir)
            self.assertEqual(str(graph.root_module.path), "<koschei-native-object>")

    def test_full_existing_check_pipeline_accepts_native_lowering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "reality")
            graph, report = check_authenticated_frontend_graph(project)
            self.assertEqual(report.functions, 1)
            self.assertEqual(report.variables, 3)
            self.assertIsNotNone(graph.mir)
            self.assertIn(self.root_id.hex(), graph.mir.modules)

    def test_installed_cli_check_and_mir_use_same_authenticated_dispatcher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "reality"
            project, handle = self.create(root)
            with object_space_check_session(self.opener(handle)):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_check(str(root), True, "en"), 0)
                check_text = stdout.getvalue()
                self.assertIn('"source": "<object-space>"', check_text)
                self.assertNotIn(self.root_id.hex(), check_text)
                self.assertNotIn(project.records[0].locator_text, check_text)

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_mir(str(root)), 0)
                mir_text = stdout.getvalue()
                self.assertIn("<object-1>", mir_text)
                self.assertNotIn(self.root_id.hex(), mir_text)
                self.assertNotIn(project.records[0].locator_text, mir_text)

    def test_legacy_graph_schema_remains_explicit_migration_compatibility(self) -> None:
        legacy_project_id = bytes.fromhex("81" * 16)
        legacy_root_id = bytes.fromhex("82" * 16)
        legacy_objects = {legacy_root_id: b"fn main() { println(7) }\n"}
        legacy_secret = encode_object_space_graph_secret(
            project_id=legacy_project_id,
            root_object_id=legacy_root_id,
            objects=legacy_objects,
            target_by_import_slot={},
        )
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = create_object_space_project(
                Path(temporary) / "legacy",
                provider=self.provider,
                temporal_key=self.temporal_key,
                objects=legacy_objects,
                root_object_id=legacy_root_id,
                graph_secret=legacy_secret,
                temporal_policy=self.policy,
                now=self.now,
                project_id=legacy_project_id,
            )
            graph, report = check_object_space_graph_by_authenticated_frontend(project)
            self.assertEqual(graph.root, legacy_root_id.hex())
            self.assertEqual(report.functions, 1)


if __name__ == "__main__":
    unittest.main()
