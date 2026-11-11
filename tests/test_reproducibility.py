from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from koschei.build_manifest import load_native_manifest
from koschei.cli_entry import main
from koschei.reproducibility import (
    ReproducibilityError,
    compare_verified_builds,
    write_reproducibility_report,
)


class ReproducibilityTests(unittest.TestCase):
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
    def test_cli_compares_two_verified_artifact_copies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, lockfile, artifact, manifest = self._build(directory)
            second_dir = Path(directory) / "second"
            second_dir.mkdir()
            second_artifact = second_dir / "app"
            shutil.copyfile(artifact, second_artifact)
            report_path = Path(directory) / "reproducibility.json"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
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
                        str(second_artifact),
                        "--right-manifest",
                        str(manifest),
                        "--right-lockfile",
                        str(lockfile),
                        "--output",
                        str(report_path),
                    ]
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(report["status"], "byte_identical")
            self.assertTrue(report["comparable"])
            self.assertTrue(report["byte_reproducible"])
            self.assertEqual(report["input_mismatches"], [])
            self.assertEqual(len(report["report_digest"]), 64)
            self.assertIn("BYTE-IDENTICAL", output.getvalue())

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_cli_rejects_tampered_second_artifact_before_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, lockfile, artifact, manifest = self._build(directory)
            second_dir = Path(directory) / "second"
            second_dir.mkdir()
            second_artifact = second_dir / "app"
            shutil.copyfile(artifact, second_artifact)
            second_artifact.write_bytes(second_artifact.read_bytes() + b"tamper")

            exit_code = main(
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
                    str(second_artifact),
                    "--right-manifest",
                    str(manifest),
                    "--right-lockfile",
                    str(lockfile),
                ]
            )

            self.assertEqual(exit_code, 1)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_comparison_distinguishes_input_and_artifact_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, manifest_path = self._build(directory)
            manifest = load_native_manifest(manifest_path)

            artifact_changed = replace(
                manifest,
                artifact_sha256="f" * 64,
                manifest_digest="e" * 64,
            )
            artifact_report = compare_verified_builds(manifest, artifact_changed)
            self.assertEqual(artifact_report.status, "artifact_mismatch")
            self.assertTrue(artifact_report.comparable)
            self.assertFalse(artifact_report.byte_reproducible)

            input_changed = replace(
                manifest,
                mir_fingerprint="d" * 64,
                artifact_sha256="c" * 64,
                manifest_digest="b" * 64,
            )
            input_report = compare_verified_builds(manifest, input_changed)
            self.assertEqual(input_report.status, "not_comparable")
            self.assertFalse(input_report.comparable)
            self.assertIn("mir_fingerprint", input_report.input_mismatches)

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_report_is_not_overwritten_silently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, manifest_path = self._build(directory)
            manifest = load_native_manifest(manifest_path)
            report = compare_verified_builds(manifest, manifest)
            destination = Path(directory) / "report.json"
            write_reproducibility_report(report, destination)

            with self.assertRaises(ReproducibilityError):
                write_reproducibility_report(report, destination)


if __name__ == "__main__":
    unittest.main()
