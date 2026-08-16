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
from koschei.native_cell_projection_v1 import (
    NativeCellProjectionError,
    _HEADER,
    decode_native_cell_projection_graph,
    encode_native_cell_projection_graph_secret,
)
from koschei.native_cell_realities_v1 import _CELL
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellProjectionAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("f1" * 16)
        self.root_id = bytes.fromhex("f2" * 16)
        self.schema_id = bytes.fromhex("f3" * 16)
        self.names = ("amount", "approved", "label")
        self.source = (
            b"witness amount 42\n"
            b"witness approved truth yes\n"
            b"witness label glyphs 4 paid\n"
            b"resolve amount\n"
            b"resolve approved\n"
            b"resolve label\n"
        )
        self.secret = encode_native_cell_projection_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects={self.root_id: self.source},
            schema_id=self.schema_id,
            cell_witnesses=self.names,
            selected_ordinal=1,
        )

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects={self.root_id: self.source},
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

    @staticmethod
    def repack_header(payload: bytes, *, selected_ordinal=None, selected_domain=None) -> bytes:
        values = list(_HEADER.unpack_from(payload, 0))
        if selected_ordinal is not None:
            values[-2] = selected_ordinal
        if selected_domain is not None:
            values[-1] = selected_domain
        return _HEADER.pack(*values) + payload[_HEADER.size:]

    def test_selected_ordinal_is_bounded_at_encode_boundary(self) -> None:
        for ordinal in (-1, 3, 100):
            with self.subTest(ordinal=ordinal), self.assertRaisesRegex(
                NativeCellProjectionError, "ordinal"
            ):
                encode_native_cell_projection_graph_secret(
                    project_id=self.project_id,
                    root_object_id=self.root_id,
                    objects={self.root_id: self.source},
                    schema_id=self.schema_id,
                    cell_witnesses=self.names,
                    selected_ordinal=ordinal,
                )

    def test_selected_domain_must_agree_with_full_schema_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            forged = replace(
                loaded,
                graph_secret=self.repack_header(loaded.graph_secret, selected_domain=1),
            )
            with self.assertRaisesRegex(NativeCellProjectionError, "full sealed schema"):
                decode_native_cell_projection_graph(forged)

    def test_unselected_cell_domain_tamper_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            forged_bytes = bytearray(loaded.graph_secret)
            # Cell 0 is unselected. Change its domain code from whole(1) to truth(2).
            forged_bytes[_HEADER.size + 36] = 2
            forged = replace(loaded, graph_secret=bytes(forged_bytes))
            with self.assertRaisesRegex(NativeCellProjectionError, "domain differs"):
                decode_native_cell_projection_graph(forged)

    def test_unselected_cell_tag_tamper_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            forged_bytes = bytearray(loaded.graph_secret)
            forged_bytes[_HEADER.size + 4] ^= 0x01
            forged = replace(loaded, graph_secret=bytes(forged_bytes))
            with self.assertRaisesRegex(NativeCellProjectionError, "does not match"):
                decode_native_cell_projection_graph(forged)

    def test_projection_tamper_is_rejected_before_interpreter_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            forged = replace(
                loaded,
                graph_secret=self.repack_header(loaded.graph_secret, selected_domain=1),
            )
            with object_space_check_session(self.opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after projection tamper"),
                ) as execute:
                    with self.assertRaises(NativeCellProjectionError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

    def test_cross_project_projection_secret_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
            with self.assertRaisesRegex(NativeCellProjectionError, "project/root"):
                decode_native_cell_projection_graph(
                    replace(loaded, project_id=bytes.fromhex("aa" * 16))
                )

    def test_public_surfaces_hide_schema_witness_and_storage_identity(self) -> None:
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
                self.schema_id.hex(),
                "amount",
                "approved",
                "label",
            ]
            needles.extend(record.locator_text for record in project.records)
            for text in (mir_text, application_go, output.getvalue()):
                for needle in needles:
                    self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
