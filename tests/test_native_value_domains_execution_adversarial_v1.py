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
from koschei.native_relationship_v1 import RELATION_GRAPH_MAGIC_V1
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_value_domains_v1 import (
    VALUE_DOMAIN_GRAPH_MAGIC_V1,
    encode_native_value_domain_graph_secret,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeValueDomainsExecutionAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("e5" * 16)
        self.root_id = bytes.fromhex("e6" * 16)
        self.source = (
            "witness left glyphs 5 hello\n"
            "witness right glyphs 5 world\n"
            "witness joined merge left right\n"
            "resolve joined\n"
        ).encode("utf-8")
        self.objects = {self.root_id: self.source}
        self.secret = encode_native_value_domain_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
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

    def test_frontend_tamper_is_rejected_before_interpreter_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            payload = bytearray(project.graph_secret)
            payload[-1] ^= 1
            forged = replace(project, graph_secret=bytes(payload))
            with object_space_check_session(self.opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after value-domain metadata tamper"),
                ) as execute:
                    with self.assertRaises(Exception) as caught:
                        cli.command_run(str(root))
                    self.assertNotIsInstance(caught.exception, AssertionError)
                    execute.assert_not_called()

    def test_schema_downgrade_never_reinterprets_value_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            payload = bytearray(project.graph_secret)
            self.assertEqual(bytes(payload[:16]), VALUE_DOMAIN_GRAPH_MAGIC_V1)
            payload[:16] = RELATION_GRAPH_MAGIC_V1
            downgraded = replace(project, graph_secret=bytes(payload))
            with object_space_check_session(self.opener(handle, project_override=downgraded)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after schema downgrade"),
                ) as execute:
                    with self.assertRaises(Exception) as caught:
                        cli.command_run(str(root))
                    self.assertNotIsInstance(caught.exception, AssertionError)
                    execute.assert_not_called()

    def test_public_run_mir_caps_and_emit_go_leak_no_storage_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            captured = io.StringIO()
            with object_space_check_session(self.opener(handle)):
                with redirect_stdout(captured), redirect_stderr(captured):
                    self.assertEqual(cli.command_run(str(root)), 0)
                    self.assertEqual(cli.command_mir(str(root)), 0)
                    self.assertEqual(cli.command_caps(str(root), True, None), 0)
                    self.assertEqual(cli.command_emit_go(str(root)), 0)

            text = captured.getvalue()
            needles = [self.project_id.hex(), self.root_id.hex()]
            needles.extend(record.locator_text for record in project.records)
            for needle in needles:
                self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
