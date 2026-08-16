from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei import cli
import koschei.object_space_commands_v1 as commands
import koschei.object_space_frontend_identity_v1 as frontend
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_frontend_identity_v1 import (
    FRONTEND_GRAPH_MAGIC_V1,
    NATIVE_WITNESS_FRONTEND_V1,
    ObjectSpaceFrontendIdentityError,
    check_object_space_graph_by_authenticated_frontend,
    decode_authenticated_frontend_graph,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project, rotate_object_space_epoch
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class AuthenticatedFrontendIdentityRedTeamV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("91" * 16)
        self.root_id = bytes.fromhex("92" * 16)
        self.source = b"witness left 40\nwitness right 2\nwitness answer sum left right\nresolve answer\n"
        self.objects = {self.root_id: self.source}
        self.secret = encode_authenticated_frontend_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            frontend_by_object={self.root_id: NATIVE_WITNESS_FRONTEND_V1},
        )

    def create(self, root: Path, *, project_id: bytes | None = None, graph_secret: bytes | None = None):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.secret if graph_secret is None else graph_secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id if project_id is None else project_id,
        )

    def opener(self, handle: bytes, *, epoch: int = 1):
        def open_project(root: Path):
            return load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=epoch,
                temporal_policy=self.policy,
                now=self.now,
            )
        return open_project

    def test_storage_epoch_rotation_preserves_authenticated_frontend_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            before, handle = self.create(root)
            before_locator = before.records[0].locator
            before_secret = before.graph_secret

            after, new_handle = rotate_object_space_epoch(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            self.assertEqual(after.epoch, 2)
            self.assertNotEqual(after.records[0].locator, before_locator)
            self.assertEqual(after.graph_secret, before_secret)
            records = decode_authenticated_frontend_graph(after)
            self.assertEqual(records[0].frontend_id, NATIVE_WITNESS_FRONTEND_V1)
            self.assertEqual(check_object_space_graph_by_authenticated_frontend(after)[0].root, self.root_id.hex())

            reopened = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=new_handle,
                expected_project_id=self.project_id,
                expected_epoch=2,
                temporal_policy=self.policy,
                now=self.now,
            )
            self.assertEqual(decode_authenticated_frontend_graph(reopened)[0].frontend_id, NATIVE_WITNESS_FRONTEND_V1)

    def test_cross_project_frontend_graph_substitution_is_rejected(self) -> None:
        other_project_id = bytes.fromhex("93" * 16)
        with tempfile.TemporaryDirectory() as temporary:
            forged, _ = self.create(
                Path(temporary) / "other",
                project_id=other_project_id,
                graph_secret=self.secret,
            )
            with self.assertRaisesRegex(ObjectSpaceFrontendIdentityError, "another project"):
                decode_authenticated_frontend_graph(forged)

    def test_exact_legacy_magic_downgrade_cannot_reinterpret_native_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self.create(Path(temporary) / "space")
            payload = bytearray(project.graph_secret)
            self.assertEqual(bytes(payload[:16]), FRONTEND_GRAPH_MAGIC_V1)
            payload[:16] = b"KOSCHEI_OSGRAPH1"
            downgraded = replace(project, graph_secret=bytes(payload))
            with patch(
                "koschei.object_space_graph_v1.parse",
                side_effect=AssertionError("legacy source parser reached during schema downgrade"),
            ):
                with self.assertRaises(Exception) as caught:
                    check_object_space_graph_by_authenticated_frontend(downgraded)
            self.assertNotIsInstance(caught.exception, AssertionError)

    def test_zero_unknown_and_mixed_frontend_bindings_fail_before_admission(self) -> None:
        with self.assertRaises(ObjectSpaceFrontendIdentityError):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects=self.objects,
                frontend_by_object={self.root_id: bytes(32)},
            )
        with self.assertRaises(ObjectSpaceFrontendIdentityError):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects=self.objects,
                frontend_by_object={self.root_id: bytes.fromhex("ff" * 32)},
            )
        second_id = bytes.fromhex("94" * 16)
        with self.assertRaises(ObjectSpaceFrontendIdentityError):
            encode_authenticated_frontend_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects={self.root_id: self.source, second_id: self.source},
                frontend_by_object={
                    self.root_id: NATIVE_WITNESS_FRONTEND_V1,
                    second_id: NATIVE_WITNESS_FRONTEND_V1,
                },
            )

    def test_run_caps_emit_go_and_build_share_authenticated_dispatch_without_identity_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            output = Path(temporary) / "program"
            captured = io.StringIO()
            with object_space_check_session(self.opener(handle)):
                with patch.object(
                    commands,
                    "check_object_space_graph",
                    wraps=frontend.check_object_space_graph_by_authenticated_frontend,
                ) as dispatcher:
                    with redirect_stdout(captured), redirect_stderr(captured):
                        cli.command_run(str(root))
                        self.assertEqual(cli.command_caps(str(root), True, None), 0)
                        self.assertEqual(cli.command_emit_go(str(root)), 0)
                        with patch.object(commands.shutil, "which", return_value=None):
                            self.assertEqual(cli.command_build(str(root), str(output), "en"), 1)
                    self.assertEqual(dispatcher.call_count, 4)

            text = captured.getvalue()
            self.assertNotIn(project.project_id.hex(), text)
            self.assertNotIn(self.root_id.hex(), text)
            self.assertNotIn(project.records[0].locator_text, text)


if __name__ == "__main__":
    unittest.main()
