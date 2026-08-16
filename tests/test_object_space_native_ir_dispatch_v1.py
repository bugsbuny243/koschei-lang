from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from koschei.native_ir_v1 import NativeIrRealityV1
from koschei.native_value_domains_v1 import WHOLE
from koschei.object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    encode_authenticated_frontend_graph_secret,
)
from koschei.object_space_native_ir_dispatch_v1 import (
    ObjectSpaceNativeIrDispatchError,
    execute_authenticated_object_space_native_ir_v1,
)
from koschei.object_space_v1 import ObjectSpaceProject, ObjectSpaceRecord


PROJECT_ID = bytes.fromhex("11" * 16)
ROOT_ID = bytes.fromhex("22" * 16)
LOCATOR = bytes.fromhex("33" * 32)


def _project(source: bytes) -> ObjectSpaceProject:
    digest = hashlib.sha256(source).digest()
    secret = encode_authenticated_frontend_graph_secret(
        project_id=PROJECT_ID,
        root_object_id=ROOT_ID,
        objects={ROOT_ID: source},
        frontend_by_object={ROOT_ID: NATIVE_WITNESS_FRONTEND_V1},
    )
    return ObjectSpaceProject(
        root=Path("/sealed/koschei"),
        project_id=PROJECT_ID,
        epoch=7,
        root_object_id=ROOT_ID,
        records=(ObjectSpaceRecord(ROOT_ID, digest, LOCATOR),),
        graph_secret=secret,
        object_payloads={ROOT_ID: source},
        unreferenced_locators=(),
    )


class ObjectSpaceNativeIrDispatchV1Tests(unittest.TestCase):
    def test_authenticated_frontend_executes_direct_native_ir(self) -> None:
        project = _project(
            b"witness base 40\n"
            b"witness fee 2\n"
            b"witness total sum base fee\n"
            b"resolve total\n"
        )
        # If the new path reaches the old compatibility graph builder, explode.
        with patch(
            "koschei.object_space_frontend_identity_v1.load_authenticated_frontend_module_graph",
            side_effect=AssertionError("legacy ModuleGraph path reached"),
        ):
            authority = execute_authenticated_object_space_native_ir_v1(project)
        self.assertEqual(authority.value.domain, WHOLE)
        self.assertEqual(authority.value.value, 42)
        self.assertIsInstance(authority.ir, NativeIrRealityV1)
        self.assertEqual(authority.frontend_id, NATIVE_WITNESS_FRONTEND_V1)

    def test_native_ir_authority_contains_no_legacy_ast_carriers(self) -> None:
        authority = execute_authenticated_object_space_native_ir_v1(
            _project(b"witness answer 42\nresolve answer\n")
        )
        forbidden = {
            "Program",
            "ModuleGraph",
            "GenericFunctionDeclaration",
            "LetStatement",
            "ReturnStatement",
            "BinaryExpression",
        }
        seen: set[int] = set()
        stack = [authority]
        while stack:
            value = stack.pop()
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            self.assertNotIn(type(value).__name__, forbidden)
            slots = getattr(type(value), "__slots__", ())
            if isinstance(slots, str):
                slots = (slots,)
            for slot in slots:
                if slot.startswith("__"):
                    continue
                child = getattr(value, slot, None)
                if isinstance(child, (tuple, list)):
                    stack.extend(child)
                elif child is not None and not isinstance(child, (bytes, str, int, bool)):
                    stack.append(child)

    def test_non_native_object_space_schema_fails_without_fallback(self) -> None:
        source = b"witness answer 42\nresolve answer\n"
        digest = hashlib.sha256(source).digest()
        project = ObjectSpaceProject(
            root=Path("/sealed/koschei"),
            project_id=PROJECT_ID,
            epoch=7,
            root_object_id=ROOT_ID,
            records=(ObjectSpaceRecord(ROOT_ID, digest, LOCATOR),),
            graph_secret=b"legacy-looking-object-space-schema",
            object_payloads={ROOT_ID: source},
            unreferenced_locators=(),
        )
        with self.assertRaises(ObjectSpaceNativeIrDispatchError):
            execute_authenticated_object_space_native_ir_v1(project)

    def test_frontend_identity_tamper_fails_before_native_execution(self) -> None:
        project = _project(b"witness answer 42\nresolve answer\n")
        tampered = bytearray(project.graph_secret)
        tampered[-32:] = bytes.fromhex("aa" * 32)
        forged = ObjectSpaceProject(
            root=project.root,
            project_id=project.project_id,
            epoch=project.epoch,
            root_object_id=project.root_object_id,
            records=project.records,
            graph_secret=bytes(tampered),
            object_payloads=project.object_payloads,
            unreferenced_locators=project.unreferenced_locators,
        )
        with patch(
            "koschei.object_space_native_ir_dispatch_v1.execute_native_ir_v1",
            side_effect=AssertionError("execution reached after frontend tamper"),
        ):
            with self.assertRaises(ObjectSpaceNativeIrDispatchError):
                execute_authenticated_object_space_native_ir_v1(forged)

    def test_opened_payload_digest_tamper_fails_before_native_execution(self) -> None:
        project = _project(b"witness answer 42\nresolve answer\n")
        forged = ObjectSpaceProject(
            root=project.root,
            project_id=project.project_id,
            epoch=project.epoch,
            root_object_id=project.root_object_id,
            records=project.records,
            graph_secret=project.graph_secret,
            object_payloads={ROOT_ID: b"witness answer 41\nresolve answer\n"},
            unreferenced_locators=project.unreferenced_locators,
        )
        with patch(
            "koschei.object_space_native_ir_dispatch_v1.execute_native_ir_v1",
            side_effect=AssertionError("execution reached after payload tamper"),
        ):
            with self.assertRaises(ObjectSpaceNativeIrDispatchError):
                execute_authenticated_object_space_native_ir_v1(forged)


if __name__ == "__main__":
    unittest.main()
