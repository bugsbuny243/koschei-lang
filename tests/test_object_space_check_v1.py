from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from koschei.cli import main
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_graph_v1 import encode_object_space_graph_secret
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceCheckV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("aa" * 16)
        self.root_id = bytes.fromhex("11" * 16)
        self.lib_id = bytes.fromhex("22" * 16)
        self.objects = {
            self.root_id: b"import lib\nfn main() { let x = lib.f() }\n",
            self.lib_id: b"fn f() -> Int { return 7 }\n",
        }
        self.secret = encode_object_space_graph_secret(
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
            graph_secret=self.secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def opener(self, handle):
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

    def invoke(self, argv: list[str]):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_check_fails_closed_without_trusted_session_broker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            self.create(root)
            code, out, err = self.invoke(["check", str(root)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("trusted session broker", err)
            self.assertNotIn(".ks' extension", err)

    def test_check_accepts_real_object_space_through_scoped_broker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, handle = self.create(root)
            with object_space_check_session(self.opener(handle)):
                code, out, err = self.invoke(["check", str(root)])
            self.assertEqual(code, 0, err)
            self.assertEqual(err, "")
            self.assertIn("KOSCHEI CHECK: PASS", out)
            self.assertIn("2 objects", out)

    def test_json_check_has_no_semantic_entry_filename_or_object_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, handle = self.create(root)
            with object_space_check_session(self.opener(handle)):
                code, out, err = self.invoke(["check", "--json", str(root)])
            self.assertEqual(code, 0, err)
            payload = json.loads(out)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["source"], "<object-space>")
            self.assertEqual(payload["modules"], 2)
            self.assertNotIn(self.root_id.hex(), out)
            self.assertNotIn(self.lib_id.hex(), out)
            self.assertNotIn("lib.ks", out)

    def test_session_scope_is_removed_after_check_context_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, handle = self.create(root)
            with object_space_check_session(self.opener(handle)):
                code, _, _ = self.invoke(["check", str(root)])
                self.assertEqual(code, 0)
            code, _, err = self.invoke(["check", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("trusted session broker", err)

    def test_broker_cannot_substitute_another_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root_a = base / "a"
            root_b = base / "b"
            _, handle_a = self.create(root_a)
            project_b, _ = self.create(root_b)

            def confused_broker(_requested: Path):
                return project_b

            with object_space_check_session(confused_broker):
                code, out, err = self.invoke(["check", str(root_a)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("different project root", err)


if __name__ == "__main__":
    unittest.main()
