from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from koschei.modules import ModuleError
from koschei.originality_contract_v1 import (
    LEGACY_SCAFFOLD_PATH_DEBT_V1,
    SurfaceProvenance,
    audit_scaffold_surface,
)
from koschei.native_reality_v1 import (
    NativeRealityError,
    REALITY_ENVELOPE_BYTES,
    create_native_reality_project,
    load_native_reality_graph,
    load_native_reality_project,
    rotate_native_reality_epoch,
)


SEAL_KEY = bytes.fromhex(
    "f38f6ac88bb9ccf847f5ef5fd27d8f20"
    "824c76532f9a145baad4619e813e73c1"
)


class NativeRealityProjectTests(unittest.TestCase):
    def test_create_has_no_manifest_entry_or_semantic_source_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            project = create_native_reality_project(root, seal_key=SEAL_KEY)

            self.assertEqual(project.reality.epoch, 1)
            self.assertEqual(len(project.reality_path.read_bytes()), REALITY_ENVELOPE_BYTES)
            self.assertEqual(project.reality_path.relative_to(root).as_posix(), ".koschei/reality")
            self.assertEqual(project.source_path.parent.relative_to(root).as_posix(), ".koschei/matter")
            self.assertRegex(project.source_path.name, r"^[0-9a-f]{32}$")

            exposed = {
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
            }
            self.assertNotIn("src", exposed)
            self.assertNotIn("src/main.ks", exposed)
            self.assertNotIn("main.ks", exposed)
            self.assertNotIn("koschei.toml", exposed)
            self.assertNotIn("README.md", exposed)
            self.assertNotIn(".gitignore", exposed)

    def test_native_layout_passes_originality_gate_with_explicit_provenance(self) -> None:
        native_static = {".koschei", ".koschei/reality", ".koschei/matter"}
        provenance = {
            ".koschei": SurfaceProvenance(
                invariant="protected-source-reality",
                rationale=(
                    "Owns the hidden Koschei reality namespace without "
                    "reusing a mainstream source-tree convention."
                ),
                collision_reviewed=True,
            ),
            ".koschei/reality": SurfaceProvenance(
                invariant="temporal-source-identity",
                rationale=(
                    "Carries authenticated project identity and epoch context "
                    "instead of a human-readable entry manifest."
                ),
                collision_reviewed=True,
            ),
            ".koschei/matter": SurfaceProvenance(
                invariant="protected-source-reality",
                rationale=(
                    "Contains role-free opaque source aliases whose physical "
                    "names are never canonical program identity."
                ),
                collision_reviewed=True,
            ),
        }
        violations = audit_scaffold_surface(
            set(LEGACY_SCAFFOLD_PATH_DEBT_V1) | native_static,
            provenance=provenance,
        )
        self.assertEqual(violations, ())

    def test_wrong_seal_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_native_reality_project(
                Path(temporary) / "demo",
                seal_key=SEAL_KEY,
            )
            with self.assertRaisesRegex(
                NativeRealityError, "authentication failed"
            ):
                load_native_reality_project(
                    project.root,
                    seal_key=b"x" * 32,
                    expected_project_id=project.reality.project_id,
                    expected_epoch=1,
                )

    def test_plain_hash_reseal_cannot_forge_authenticated_reality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_native_reality_project(
                Path(temporary) / "demo",
                seal_key=SEAL_KEY,
            )
            payload = bytearray(project.reality_path.read_bytes())
            payload[40] ^= 0x01
            payload[-32:] = hashlib.sha256(payload[:-32]).digest()
            project.reality_path.write_bytes(payload)

            with self.assertRaisesRegex(
                NativeRealityError, "authentication failed"
            ):
                load_native_reality_project(
                    project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality.project_id,
                    expected_epoch=1,
                )

    def test_source_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_native_reality_project(
                Path(temporary) / "demo",
                seal_key=SEAL_KEY,
            )
            project.source_path.write_bytes(
                project.source_path.read_bytes() + b"\n// tamper"
            )
            with self.assertRaisesRegex(NativeRealityError, "hash mismatch"):
                load_native_reality_project(
                    project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality.project_id,
                    expected_epoch=1,
                )

    def test_cross_project_replay_is_rejected_even_with_same_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = create_native_reality_project(root / "first", seal_key=SEAL_KEY)
            second = create_native_reality_project(root / "second", seal_key=SEAL_KEY)

            with self.assertRaisesRegex(NativeRealityError, "project id"):
                load_native_reality_project(
                    second.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=first.reality.project_id,
                    expected_epoch=1,
                )

    def test_epoch_rotation_changes_alias_not_canonical_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_native_reality_project(
                Path(temporary) / "demo",
                seal_key=SEAL_KEY,
            )
            old_alias = project.source_path
            rotated = rotate_native_reality_epoch(
                project.root,
                seal_key=SEAL_KEY,
                expected_project_id=project.reality.project_id,
                expected_epoch=1,
            )

            self.assertEqual(rotated.reality.epoch, 2)
            self.assertEqual(rotated.reality.project_id, project.reality.project_id)
            self.assertEqual(
                rotated.reality.root_object_id,
                project.reality.root_object_id,
            )
            self.assertEqual(
                rotated.reality.artifact_digest,
                project.reality.artifact_digest,
            )
            self.assertNotEqual(
                rotated.reality.epoch_alias,
                project.reality.epoch_alias,
            )
            self.assertFalse(old_alias.exists())

            with self.assertRaisesRegex(NativeRealityError, "temporal context"):
                load_native_reality_project(
                    rotated.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=rotated.reality.project_id,
                    expected_epoch=1,
                )

    def test_symlink_source_locator_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = create_native_reality_project(
                root / "demo",
                seal_key=SEAL_KEY,
            )
            outside = root / "outside.ks"
            outside.write_text(project.source_text, encoding="utf-8")
            project.source_path.unlink()
            try:
                project.source_path.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable on this platform")

            with self.assertRaisesRegex(
                NativeRealityError, "regular non-symlink"
            ):
                load_native_reality_project(
                    project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality.project_id,
                    expected_epoch=1,
                )

    def test_v1_imports_fail_closed_without_filename_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_native_reality_project(
                Path(temporary) / "demo",
                seal_key=SEAL_KEY,
                source_text="import x\nfn main() {}\n",
            )
            with self.assertRaises(ModuleError) as raised:
                load_native_reality_graph(
                    project.root,
                    seal_key=SEAL_KEY,
                    expected_project_id=project.reality.project_id,
                    expected_epoch=1,
                )
            self.assertEqual(raised.exception.code, "KS5701")


if __name__ == "__main__":
    unittest.main()
