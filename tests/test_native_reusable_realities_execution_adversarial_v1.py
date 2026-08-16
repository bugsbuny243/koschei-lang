from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from koschei import cli
from koschei.interpreter import Interpreter
from koschei.native_reusable_realities_v1 import (
    NativeReusableRealizationSpecV1,
    NativeReusableRealityError,
    _HEADER,
    _OBJECT,
    _REALIZATION,
    encode_native_reusable_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeReusableExecutionAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("f1" * 16)
        self.root_id = bytes.fromhex("f2" * 16)
        self.reusable_id = bytes.fromhex("f3" * 16)
        self.realization_id = bytes.fromhex("f4" * 16)
        self.objects = {
            self.root_id: b"witness value conduit 0\nresolve value\n",
            self.reusable_id: (
                b"witness left conduit 0\n"
                b"witness right conduit 1\n"
                b"witness total sum left right\n"
                b"resolve total\n"
            ),
        }
        self.secret = encode_native_reusable_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            current_epoch=1,
            realizations=(
                NativeReusableRealizationSpecV1(
                    realization_id=self.realization_id,
                    root_slot=0,
                    reusable_object_id=self.reusable_id,
                    inputs=(40, 2),
                    issued_epoch=1,
                    expires_epoch=2,
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

    def opener(self, handle: bytes, *, project_override=None):
        def open_project(path: Path):
            if project_override is not None:
                return project_override
            return load_object_space_project(
                path,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
        return open_project

    def test_authority_inflation_is_rejected_before_interpreter_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            forged_bytes = bytearray(project.graph_secret)
            record_offset = _HEADER.size + len(project.records) * _OBJECT.size
            authority_offset = record_offset + _REALIZATION.size - 16
            struct.pack_into(">Q", forged_bytes, authority_offset, 1)
            forged = replace(project, graph_secret=bytes(forged_bytes))

            with object_space_check_session(self.opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after reusable authority inflation"),
                ) as execute:
                    with self.assertRaises(NativeReusableRealityError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

    def test_public_surfaces_hide_reusable_and_realization_storage_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            output = io.StringIO()
            with object_space_check_session(self.opener(handle)):
                checked_project, graph = commands._checked(str(root))
                mir_text = repr(commands._public_mir_payload(graph, checked_project))
                go_source = commands._object_space_go_source(str(root))[1]
                main_start = go_source.rfind("func main()")
                self.assertGreaterEqual(main_start, 0)
                application_go = go_source[main_start:]
                with redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli.command_caps(str(root), True, None), 0)
                    self.assertEqual(cli.command_run(str(root)), 0)

            needles = [
                self.project_id.hex(),
                self.root_id.hex(),
                self.reusable_id.hex(),
                self.realization_id.hex(),
            ]
            needles.extend(record.locator_text for record in project.records)
            for text in (mir_text, application_go, output.getvalue()):
                for needle in needles:
                    self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
