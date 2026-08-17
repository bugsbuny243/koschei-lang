from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from koschei.canonical_native_entrypoints_v1 import (
    check_canonical_native_v1,
    run_canonical_native_v1,
)
from koschei.native_value_domains_v1 import WHOLE
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_native_ir_dispatch_v1 import ObjectSpaceNativeIrDispatchError
from koschei.object_space_v1 import ObjectSpaceProject, ObjectSpaceRecord


PROJECT_ID = bytes.fromhex("41" * 16)
ROOT_ID = bytes.fromhex("42" * 16)
LOCATOR = bytes.fromhex("43" * 32)


def _project(source: bytes, *, graph_secret: bytes | None = None) -> ObjectSpaceProject:
    digest = hashlib.sha256(source).digest()
    secret = graph_secret
    if secret is None:
        secret = encode_authenticated_frontend_graph_secret(
            project_id=PROJECT_ID,
            root_object_id=ROOT_ID,
            objects={ROOT_ID: source},
            frontend_by_object={ROOT_ID: NATIVE_WITNESS_FRONTEND_V1},
        )
    return ObjectSpaceProject(
        root=Path("/sealed/canonical-native-v1"),
        project_id=PROJECT_ID,
        epoch=9,
        root_object_id=ROOT_ID,
        records=(ObjectSpaceRecord(ROOT_ID, digest, LOCATOR),),
        graph_secret=secret,
        object_payloads={ROOT_ID: source},
        unreferenced_locators=(),
    )


class CanonicalNativeEntrypointsV1Tests(unittest.TestCase):
    def test_check_lowers_authenticated_object_space_without_execution(self) -> None:
        project = _project(
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n"
        )
        with patch(
            "koschei.object_space_native_ir_dispatch_v1.execute_native_ir_v1",
            side_effect=AssertionError("check must not execute"),
        ):
            authority = check_canonical_native_v1(project)
        self.assertEqual(authority.project_id, PROJECT_ID)
        self.assertEqual(authority.epoch, 9)
        self.assertEqual(authority.ir.resolve, "total")

    def test_run_executes_native_ir_and_never_builds_legacy_graph(self) -> None:
        project = _project(
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n"
        )
        with patch(
            "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
            side_effect=AssertionError("legacy ModuleGraph path reached"),
        ):
            authority = run_canonical_native_v1(project)
        self.assertEqual(authority.value.domain, WHOLE)
        self.assertEqual(authority.value.value, 42)

    def test_unsupported_schema_fails_closed_for_check_and_run(self) -> None:
        project = _project(
            b"witness answer 42\nresolve answer\n",
            graph_secret=b"unsupported-authenticated-shape",
        )
        with self.assertRaises(ObjectSpaceNativeIrDispatchError):
            check_canonical_native_v1(project)
        with self.assertRaises(ObjectSpaceNativeIrDispatchError):
            run_canonical_native_v1(project)

    def test_filename_and_source_appearance_are_not_dispatch_authority(self) -> None:
        legacy_looking = _project(
            b"fn main() {\n  return 42\n}\n",
        )
        with patch(
            "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
            side_effect=AssertionError("legacy fallback reached"),
        ):
            with self.assertRaises(ObjectSpaceNativeIrDispatchError):
                run_canonical_native_v1(legacy_looking)


if __name__ == "__main__":
    unittest.main()
