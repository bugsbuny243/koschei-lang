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
from koschei.native_cell_realities_v1 import (
    NativeCellRealityError,
    _CELL,
    _HEADER,
    decode_native_cell_graph,
    encode_native_cell_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellRealitiesAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("b1" * 16)
        self.root_id = bytes.fromhex("b2" * 16)
        self.schema_id = bytes.fromhex("b3" * 16)
        self.source = (
            b"witness amount 42\n"
            b"witness approved truth yes\n"
            b"witness label glyphs 4 paid\n"
            b"resolve amount\n"
            b"resolve approved\n"
            b"resolve label\n"
        )
        self.secret = encode_native_cell_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects={self.root_id: self.source},
            schema_id=self.schema_id,
            cell_witnesses=("amount", "approved", "label"),
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

    def test_schema_identity_must_be_nonzero_and_exact(self) -> None:
        with self.assertRaisesRegex(NativeCellRealityError, "schema id"):
            encode_native_cell_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects={self.root_id: self.source},
                schema_id=bytes(16),
                cell_witnesses=("amount", "approved", "label"),
            )

    def test_source_resolve_set_must_exactly_match_sealed_cells(self) -> None:
        with self.assertRaisesRegex(NativeCellRealityError, "resolve set"):
            encode_native_cell_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects={self.root_id: self.source},
                schema_id=self.schema_id,
                cell_witnesses=("amount", "approved"),
            )

    def test_dormant_witness_outside_cell_union_is_rejected(self) -> None:
        dormant = self.source.replace(
            b"resolve amount\n",
            b"witness hidden 99\nresolve amount\n",
        )
        with self.assertRaisesRegex(NativeCellRealityError, "dormant"):
            encode_native_cell_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                objects={self.root_id: dormant},
                schema_id=self.schema_id,
                cell_witnesses=("amount", "approved", "label"),
            )

    def test_cell_domain_tag_and_ordinal_tamper_fail_closed(self) -> None:
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

            domain_forged = bytearray(loaded.graph_secret)
            domain_offset = _HEADER.size + 36
            struct.pack_into("B", domain_forged, domain_offset, 9)
            with self.assertRaisesRegex(NativeCellRealityError, "domain code"):
                decode_native_cell_graph(replace(loaded, graph_secret=bytes(domain_forged)))

            ordinal_forged = bytearray(loaded.graph_secret)
            second_offset = _HEADER.size + _CELL.size
            struct.pack_into(">H", ordinal_forged, second_offset, 0)
            with self.assertRaisesRegex(NativeCellRealityError, "ordinal"):
                decode_native_cell_graph(replace(loaded, graph_secret=bytes(ordinal_forged)))

            tag_forged = bytearray(loaded.graph_secret)
            tag_offset = _HEADER.size + 4
            tag_forged[tag_offset] ^= 0x01
            with self.assertRaisesRegex(NativeCellRealityError, "does not match"):
                decode_native_cell_graph(replace(loaded, graph_secret=bytes(tag_forged)))

    def test_cross_project_secret_replay_is_rejected(self) -> None:
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
            forged = replace(loaded, project_id=bytes.fromhex("c1" * 16))
            with self.assertRaisesRegex(NativeCellRealityError, "project/root"):
                decode_native_cell_graph(forged)

    def test_metadata_tamper_is_rejected_before_interpreter_execution(self) -> None:
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

            with object_space_check_session(self.opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after cell metadata tamper"),
                ) as execute:
                    with self.assertRaises(NativeCellRealityError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

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
