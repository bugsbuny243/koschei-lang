from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from koschei import cli
from koschei.object_space_check_v1 import ObjectSpaceCheckSessionError
from koschei.object_space_commands_v1 import ObjectSpaceCommandError, object_space_session
from koschei.object_space_graph_v1 import encode_object_space_graph_secret
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceCommandsV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("a1" * 16)
        self.root_id = bytes.fromhex("b2" * 16)
        self.lib_id = bytes.fromhex("c3" * 16)
        self.objects = {
            self.root_id: b"import lib\nfn main() { println(7) }\n",
            self.lib_id: b"fn guarded(c: DiskCaps) -> Int { return 7 }\n",
        }
        self.graph_secret = encode_object_space_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            target_by_import_slot={self.root_id: (self.lib_id,)},
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

    def assert_no_storage_identity(self, text: str, project) -> None:
        self.assertNotIn(self.project_id.hex(), text)
        self.assertNotIn(self.root_id.hex(), text)
        self.assertNotIn(self.lib_id.hex(), text)
        for record in project.records:
            self.assertNotIn(record.locator_text, text)

    def test_run_mir_caps_and_emit_go_share_one_scoped_object_space_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "reality"
            project, handle = self.create(root)
            with object_space_session(self.opener(handle)):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_run(str(root)), 0)
                self.assertEqual(stdout.getvalue(), "7\n")

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_mir(str(root)), 0)
                mir_text = stdout.getvalue()
                self.assertIn('"root": "<object-', mir_text)
                self.assert_no_storage_identity(mir_text, project)

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_caps(str(root), True, None), 0)
                caps_text = stdout.getvalue()
                self.assertIn('"source": "<object-space>"', caps_text)
                self.assertIn("<object-", caps_text)
                self.assert_no_storage_identity(caps_text, project)

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.command_emit_go(str(root)), 0)
                go_source = stdout.getvalue()
                self.assertIn("func ksfn_main() any", go_source)
                self.assertIn("cell", go_source)
                self.assert_no_storage_identity(go_source, project)

    def test_object_space_commands_fail_closed_without_session_broker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "reality"
            self.create(root)
            with self.assertRaises(ObjectSpaceCheckSessionError):
                cli.command_run(str(root))
            with self.assertRaises(ObjectSpaceCheckSessionError):
                cli.command_mir(str(root))
            with self.assertRaises(ObjectSpaceCheckSessionError):
                cli.command_caps(str(root), False, None)
            with self.assertRaises(ObjectSpaceCheckSessionError):
                cli.command_emit_go(str(root))

    def test_build_requires_explicit_external_output_and_never_derives_entry_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "reality"
            _, handle = self.create(root)
            with object_space_session(self.opener(handle)):
                with self.assertRaisesRegex(ObjectSpaceCommandError, "explicit"):
                    cli.command_build(str(root), None, "en")
                with self.assertRaisesRegex(ObjectSpaceCommandError, "inside"):
                    cli.command_build(str(root), str(root / "artifact"), "en")

    def test_build_uses_generated_identity_clean_source_for_external_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "reality"
            _, handle = self.create(root)
            target = base / "product-image"
            completed = SimpleNamespace(returncode=0, stderr="")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with object_space_session(self.opener(handle)):
                with patch(
                    "koschei.object_space_commands_v1.shutil.which",
                    return_value="/usr/bin/go",
                ), patch(
                    "koschei.object_space_commands_v1.subprocess.run",
                    return_value=completed,
                ) as run:
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        self.assertEqual(
                            cli.command_build(str(root), str(target), "en"),
                            0,
                        )
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn(str(target.resolve()), stdout.getvalue())
            args, kwargs = run.call_args
            self.assertEqual(args[0][0], "/usr/bin/go")
            self.assertIn(str(target.resolve()), args[0])
            self.assertTrue(kwargs["capture_output"])


if __name__ == "__main__":
    unittest.main()
