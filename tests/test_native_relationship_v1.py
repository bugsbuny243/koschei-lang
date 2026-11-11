from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from koschei import cli
from koschei.native_relationship_originality_v1 import audit_native_relationship_surface_v1
from koschei.native_relationship_v1 import (
    NATIVE_RELATIONSHIP_FRONTEND_V1,
    NativeRelationshipSpecV1,
    check_native_relationship_object_space,
    decode_native_relationship_graph,
    encode_native_relationship_graph_secret,
)
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeRelationshipV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("a1" * 16)
        self.root_id = bytes.fromhex("a2" * 16)
        self.target_id = bytes.fromhex("a3" * 16)
        self.relation_id = bytes.fromhex("a4" * 16)
        self.root_source = (
            b"witness remote conduit 0\n"
            b"witness fee 2\n"
            b"witness total sum remote fee\n"
            b"resolve total\n"
        )
        self.target_source = (
            b"witness base 20\n"
            b"witness doubled product base 2\n"
            b"resolve doubled\n"
        )
        self.objects = {
            self.root_id: self.root_source,
            self.target_id: self.target_source,
        }
        self.secret = encode_native_relationship_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            current_epoch=1,
            relationships=(
                NativeRelationshipSpecV1(
                    relation_id=self.relation_id,
                    slot=0,
                    target_object_id=self.target_id,
                    issued_epoch=1,
                    expires_epoch=4,
                    max_target_witnesses=2,
                    max_abs_value=40,
                ),
            ),
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

    def test_two_object_sealed_value_relationship_resolves_42(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "space")
            checked = decode_native_relationship_graph(project)
            self.assertEqual(checked.targets[self.target_id].value, 40)
            self.assertEqual(checked.root.value, 42)
            self.assertEqual(checked.relations[0].relation_id, self.relation_id)
            self.assertEqual(checked.relations[0].authority_ceiling, 0)
            self.assertEqual(checked.relations[0].effect_ceiling, 0)

    def test_relationship_frontend_is_distinct_from_leaf_witness_frontend(self) -> None:
        self.assertEqual(len(NATIVE_RELATIONSHIP_FRONTEND_V1), 32)
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "space")
            graph, report = check_native_relationship_object_space(project)
            self.assertEqual(graph.root, self.root_id.hex())
            self.assertEqual(report.functions, 1)
            self.assertEqual(report.variables, 3)
            self.assertIsNotNone(graph.mir)

    def test_installed_check_and_mir_dispatch_without_storage_identity_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            with object_space_check_session(self.opener(handle)):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_check(str(root), True, "en"), 0)
                    self.assertEqual(cli.command_mir(str(root)), 0)
                text = stdout.getvalue()
            self.assertNotIn(self.project_id.hex(), text)
            self.assertNotIn(self.root_id.hex(), text)
            self.assertNotIn(self.target_id.hex(), text)
            self.assertNotIn(self.relation_id.hex(), text)
            for record in project.records:
                self.assertNotIn(record.locator_text, text)

    def test_conduit_source_has_no_import_module_path_or_namespace_surface(self) -> None:
        text = self.root_source.decode("ascii")
        for forbidden in ("import", "module", "package", "src", ".ks", "::", "from", "use"):
            self.assertNotIn(forbidden, text)
        self.assertIn("conduit 0", text)

    def test_relationship_word_passes_originality_contract(self) -> None:
        self.assertEqual(audit_native_relationship_surface_v1(), ())


if __name__ == "__main__":
    unittest.main()
