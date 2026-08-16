from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from koschei import cli
from koschei.object_space_check_v1 import ObjectSpaceCheckSessionError
from koschei.object_space_commands_v1 import (
    ObjectSpaceCommandError,
    _target_inside_project,
    object_space_session,
)
from koschei.object_space_graph_v1 import encode_object_space_graph_secret
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceCommandsAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("31" * 16)
        self.root_id = bytes.fromhex("42" * 16)
        self.lib_id = bytes.fromhex("53" * 16)
        self.objects = {
            self.root_id: b"import helper\nfn main() { println(helper.answer()) }\n",
            self.lib_id: b"fn answer() -> Int { return 9 }\n",
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

    def test_symlink_root_is_routed_to_object_space_and_never_legacy_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "reality"
            self.create(root)
            alias = base / "alias"
            alias.symlink_to(root, target_is_directory=True)

            def legacy_bomb(*_args, **_kwargs):
                raise AssertionError("legacy resolver was reached")

            with patch(
                "koschei.object_space_commands_v1._ORIGINAL_COMMAND_RUN",
                legacy_bomb,
            ):
                with self.assertRaises(ObjectSpaceCheckSessionError):
                    cli.command_run(str(alias))

    def test_partial_object_space_is_not_allowed_to_fall_back_for_compiler_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "partial"
            root.mkdir()
            (root / "k0").write_bytes(b"malformed")

            def legacy_bomb(*_args, **_kwargs):
                raise AssertionError("legacy resolver was reached")

            patches = (
                patch("koschei.object_space_commands_v1._ORIGINAL_COMMAND_RUN", legacy_bomb),
                patch("koschei.object_space_commands_v1._ORIGINAL_COMMAND_MIR", legacy_bomb),
                patch("koschei.object_space_commands_v1._ORIGINAL_COMMAND_CAPS", legacy_bomb),
                patch("koschei.object_space_commands_v1._ORIGINAL_COMMAND_EMIT_GO", legacy_bomb),
                patch("koschei.object_space_commands_v1._ORIGINAL_COMMAND_BUILD", legacy_bomb),
            )
            for item in patches:
                item.start()
            try:
                with self.assertRaises(ObjectSpaceCheckSessionError):
                    cli.command_run(str(root))
                with self.assertRaises(ObjectSpaceCheckSessionError):
                    cli.command_mir(str(root))
                with self.assertRaises(ObjectSpaceCheckSessionError):
                    cli.command_caps(str(root), False, None)
                with self.assertRaises(ObjectSpaceCheckSessionError):
                    cli.command_emit_go(str(root))
                with self.assertRaises(ObjectSpaceCheckSessionError):
                    cli.command_build(str(root), str(Path(temporary) / "out"), "en")
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_build_rejects_lexical_path_inside_project_even_when_symlink_points_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "reality"
            project, _ = self.create(root)
            outside = base / "outside-image"
            link = root / "artifact"
            link.symlink_to(outside)
            self.assertTrue(_target_inside_project(link, project))

            # Return the already authenticated immutable view so the attack tests
            # the output boundary itself rather than being stopped earlier by a
            # future stricter root-listing admission rule.
            with object_space_session(lambda _requested: project):
                with self.assertRaisesRegex(ObjectSpaceCommandError, "inside"):
                    cli.command_build(str(root), str(link), "en")
            self.assertFalse(outside.exists())

    def test_build_rejects_external_lexical_path_that_resolves_back_inside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "reality"
            project, _ = self.create(root)
            outside_alias = base / "outside-alias"
            outside_alias.symlink_to(root, target_is_directory=True)
            candidate = outside_alias / "artifact"
            self.assertTrue(_target_inside_project(candidate, project))

    def test_native_build_fails_closed_without_proven_memory_backed_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "reality"
            _, handle = self.create(root)
            target = base / "binary"
            with object_space_session(self.opener(handle)):
                with patch(
                    "koschei.object_space_commands_v1.shutil.which",
                    return_value="/usr/bin/go",
                ), patch(
                    "koschei.object_space_commands_v1._memory_backed_workspace_root",
                    return_value=None,
                ), patch(
                    "koschei.object_space_commands_v1.subprocess.run",
                ) as run:
                    with self.assertRaisesRegex(ObjectSpaceCommandError, "memory-backed"):
                        cli.command_build(str(root), str(target), "en")
                    run.assert_not_called()

    def test_native_build_stages_backend_source_with_owner_only_modes_in_admitted_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "reality"
            project, handle = self.create(root)
            target = base / "binary"
            scratch = base / "memory-fixture"
            scratch.mkdir(mode=0o700)
            inspected = {"done": False}

            def fake_run(args, *, cwd, capture_output, text):
                workspace = Path(cwd)
                self.assertEqual(workspace.parent, scratch)
                source = workspace / "main.go"
                module = workspace / "go.mod"
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(module.stat().st_mode), 0o600)
                generated = source.read_text(encoding="utf-8")
                self.assertNotIn(project.project_id.hex(), generated)
                self.assertNotIn(self.root_id.hex(), generated)
                self.assertNotIn(self.lib_id.hex(), generated)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                self.assertEqual(args[0], "/usr/bin/go")
                inspected["done"] = True
                return SimpleNamespace(returncode=0, stderr="")

            with object_space_session(self.opener(handle)):
                with patch(
                    "koschei.object_space_commands_v1.shutil.which",
                    return_value="/usr/bin/go",
                ), patch(
                    "koschei.object_space_commands_v1._memory_backed_workspace_root",
                    return_value=scratch,
                ), patch(
                    "koschei.object_space_commands_v1.subprocess.run",
                    side_effect=fake_run,
                ):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(cli.command_build(str(root), str(target), "en"), 0)
            self.assertTrue(inspected["done"])
            self.assertIn(str(target.resolve()), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
