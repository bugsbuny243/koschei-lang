from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from koschei.build_manifest import load_native_manifest
from koschei.cli_entry import main
from koschei.release_proof import (
    ReleaseProofError,
    build_release_proof,
    load_release_proof,
    write_release_proof,
)
from koschei.reproducibility import compare_verified_builds


class ReleaseProofTests(unittest.TestCase):
    def _build(self, directory: str) -> tuple[Path, Path, Path, Path]:
        root = Path(directory)
        source = root / "main.ks"
        lockfile = root / "koschei.lock.json"
        artifact = root / "app"
        manifest = root / "app.build.json"
        source.write_text("fn main() {\n    return\n}\n", encoding="utf-8")
        self.assertEqual(
            main(["lock", "create", str(source), "--output", str(lockfile)]),
            0,
        )
        self.assertEqual(
            main(
                [
                    "build",
                    str(source),
                    "--locked",
                    "--lockfile",
                    str(lockfile),
                    "--output",
                    str(artifact),
                    "--build-manifest",
                    str(manifest),
                ]
            ),
            0,
        )
        return source, lockfile, artifact, manifest

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_cli_creates_and_verifies_release_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, lockfile, artifact, manifest = self._build(directory)
            witness_dir = Path(directory) / "witness"
            witness_dir.mkdir()
            witness_artifact = witness_dir / "app"
            shutil.copyfile(artifact, witness_artifact)
            report = Path(directory) / "reproducibility.json"
            proof = Path(directory) / "release-proof.json"

            common = [
                "--release-source",
                str(source),
                "--release-artifact",
                str(artifact),
                "--release-manifest",
                str(manifest),
                "--release-lockfile",
                str(lockfile),
                "--witness-source",
                str(source),
                "--witness-artifact",
                str(witness_artifact),
                "--witness-manifest",
                str(manifest),
                "--witness-lockfile",
                str(lockfile),
            ]

            self.assertEqual(
                main(
                    [
                        "build-compare",
                        "--left-source",
                        str(source),
                        "--left-artifact",
                        str(artifact),
                        "--left-manifest",
                        str(manifest),
                        "--left-lockfile",
                        str(lockfile),
                        "--right-source",
                        str(source),
                        "--right-artifact",
                        str(witness_artifact),
                        "--right-manifest",
                        str(manifest),
                        "--right-lockfile",
                        str(lockfile),
                        "--output",
                        str(report),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "release-proof",
                        "create",
                        *common,
                        "--report",
                        str(report),
                        "--output",
                        str(proof),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "release-proof",
                        "verify",
                        *common,
                        "--report",
                        str(report),
                        "--proof",
                        str(proof),
                    ]
                ),
                0,
            )

            payload = json.loads(proof.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "verified_reproducible_release_candidate")
            self.assertTrue(payload["byte_reproducible"])
            self.assertTrue(payload["owner_approval_required"])
            self.assertFalse(payload["automatic_publish_allowed"])
            self.assertFalse(payload["package_registry_write_allowed"])
            self.assertFalse(payload["production_integration_allowed"])
            self.assertEqual(
                payload["release_artifact_sha256"],
                payload["witness_artifact_sha256"],
            )

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_non_reproducible_build_cannot_become_release_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, manifest_path = self._build(directory)
            release = load_native_manifest(manifest_path)
            witness = replace(
                release,
                artifact_sha256="f" * 64,
                manifest_digest="e" * 64,
            )
            report = compare_verified_builds(release, witness)

            with self.assertRaises(ReleaseProofError):
                build_release_proof(release, witness, report)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_release_proof_tamper_and_overwrite_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, manifest_path = self._build(directory)
            manifest = load_native_manifest(manifest_path)
            report = compare_verified_builds(manifest, manifest)
            proof = build_release_proof(manifest, manifest, report)
            path = Path(directory) / "proof.json"
            write_release_proof(proof, path)

            with self.assertRaises(ReleaseProofError):
                write_release_proof(proof, path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["automatic_publish_allowed"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReleaseProofError):
                load_release_proof(path)


if __name__ == "__main__":
    unittest.main()
