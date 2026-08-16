from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei import cli
from koschei.interpreter import Interpreter
from koschei.native_relationship_v1 import (
    NativeRelationshipError,
    NativeRelationshipSpecV1,
    encode_native_relationship_graph_secret,
)
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeRelationshipExecutionAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("e1" * 16)
        self.root_id = bytes.fromhex("e2" * 16)
        self.target_id = bytes.fromhex("e3" * 16)
        self.relation_id = bytes.fromhex("e4" * 16)
        self.objects = {
            self.root_id: (
                b"witness remote conduit 0\n"
                b"witness fee 2\n"
                b"witness total sum remote fee\n"
                b"resolve total\n"
            ),
            self.target_id: b"witness answer 40\nresolve answer\n",
        }

    def _secret(self, *, expires_epoch: int = 2) -> bytes:
        return encode_native_relationship_graph_secret(
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
                    expires_epoch=expires_epoch,
                    max_target_witnesses=1,
                    max_abs_value=40,
                ),
            ),
        )

    def _create(self, root: Path, *, expires_epoch: int = 2):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self._secret(expires_epoch=expires_epoch),
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def _opener(self, handle: bytes, *, epoch: int = 1, project_override=None):
        def open_project(path: Path):
            if project_override is not None:
                return project_override
            return load_object_space_project(
                path,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=epoch,
                temporal_policy=self.policy,
                now=self.now,
            )
        return open_project

    def test_tampered_relationship_is_rejected_before_interpreter_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self._create(root)
            payload = bytearray(project.graph_secret)
            payload[-1] ^= 1
            forged = replace(project, graph_secret=bytes(payload))

            with object_space_check_session(self._opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after relationship tamper"),
                ) as execute:
                    with self.assertRaises(NativeRelationshipError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

    def test_successful_public_run_leaks_no_project_object_relation_or_locator_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self._create(root)
            output = io.StringIO()
            with object_space_check_session(self._opener(handle)):
                with redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli.command_run(str(root)), 0)

            text = output.getvalue()
            needles = [
                self.project_id.hex(),
                self.root_id.hex(),
                self.target_id.hex(),
                self.relation_id.hex(),
            ]
            needles.extend(record.locator_text for record in project.records)
            for needle in needles:
                self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
