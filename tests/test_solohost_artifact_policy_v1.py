from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools" / "verify_solohost_artifact_v1.py"
ASSEMBLER = ROOT / "tools" / "assemble_solohost_staging_v1.py"
SIGNER = ROOT / "tools" / "sign_solohost_release_v1.py"


class SoloHostArtifactPolicyV1Tests(unittest.TestCase):
    def _verify(
        self,
        artifact: Path,
        *,
        allow_unsigned: bool = False,
        public_key: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(VERIFIER), str(artifact)]
        if allow_unsigned:
            command.append("--allow-unsigned-staging")
        if public_key is not None:
            command.extend(["--public-key", str(public_key)])
        return subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)

    def _assemble(self, binary: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(ASSEMBLER),
                "--binary",
                str(binary),
                "--output",
                str(output),
                "--version",
                "0.10.0-test",
                "--platform",
                "linux-x86_64",
                "--source-commit",
                "deadbeef",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def _generate_ed25519_keypair(self, root: Path) -> tuple[Path, Path]:
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
            check=True,
            capture_output=True,
            text=True,
        )
        return private_key, public_key

    def test_assembler_creates_digest_bound_unsigned_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"

            assembled = self._assemble(binary, artifact)
            staged = self._verify(artifact, allow_unsigned=True)
            publish = self._verify(artifact)

            self.assertEqual(assembled.returncode, 0, assembled.stdout + assembled.stderr)
            self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)
            self.assertIn("NOT PUBLISHABLE", staged.stdout)
            self.assertEqual(publish.returncode, 1)
            self.assertIn("unsigned staging; publication is blocked", publish.stdout)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required for Ed25519 release-signing test")
    def test_signed_release_passes_with_matching_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"
            self.assertEqual(self._assemble(binary, artifact).returncode, 0)
            private_key, public_key = self._generate_ed25519_keypair(root)

            signed = subprocess.run(
                [sys.executable, str(SIGNER), str(artifact), "--private-key", str(private_key)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            verified = self._verify(artifact, public_key=public_key)

            self.assertEqual(signed.returncode, 0, signed.stdout + signed.stderr)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertIn("signed publication gate", verified.stdout)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required for Ed25519 release-signing test")
    def test_signed_release_rejects_wrong_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"
            self.assertEqual(self._assemble(binary, artifact).returncode, 0)
            private_key, _ = self._generate_ed25519_keypair(root)
            wrong_root = root / "wrong"
            wrong_root.mkdir()
            _, wrong_public_key = self._generate_ed25519_keypair(wrong_root)
            self.assertEqual(
                subprocess.run(
                    [sys.executable, str(SIGNER), str(artifact), "--private-key", str(private_key)],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                ).returncode,
                0,
            )

            result = self._verify(artifact, public_key=wrong_public_key)

            self.assertEqual(result.returncode, 1)
            self.assertIn("key_id does not match supplied public key", result.stdout)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required for Ed25519 release-signing test")
    def test_signed_release_rejects_manifest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"
            self.assertEqual(self._assemble(binary, artifact).returncode, 0)
            private_key, public_key = self._generate_ed25519_keypair(root)
            self.assertEqual(
                subprocess.run(
                    [sys.executable, str(SIGNER), str(artifact), "--private-key", str(private_key)],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                ).returncode,
                0,
            )
            manifest = artifact / "koschei-release-manifest.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")

            result = self._verify(artifact, public_key=public_key)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Ed25519 signature verification failed", result.stdout)

    def test_rejects_tampered_executable_after_manifest_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"
            self.assertEqual(self._assemble(binary, artifact).returncode, 0)
            (artifact / "ks").write_bytes(b"tampered")

            result = self._verify(artifact, allow_unsigned=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("sha256 does not match executable bytes", result.stdout)
            self.assertIn("size_bytes does not match executable bytes", result.stdout)

    def test_rejects_python_source_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"
            self.assertEqual(self._assemble(binary, artifact).returncode, 0)
            leaked = artifact / "koschei"
            leaked.mkdir()
            (leaked / "compiler.py").write_text("print('private source')\n", encoding="utf-8")

            result = self._verify(artifact, allow_unsigned=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden source suffix .py", result.stdout)

    def test_rejects_private_repository_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "input-koschei"
            binary.write_bytes(b"sealed-executable-placeholder")
            artifact = root / "artifact"
            self.assertEqual(self._assemble(binary, artifact).returncode, 0)
            git_dir = artifact / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("private\n", encoding="utf-8")

            result = self._verify(artifact, allow_unsigned=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden private/source path component", result.stdout)

    def test_assembler_rejects_python_as_customer_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "compiler.py"
            source.write_text("print('no')\n", encoding="utf-8")
            artifact = root / "artifact"

            result = self._assemble(source, artifact)

            self.assertEqual(result.returncode, 2)
            self.assertIn("must be a built executable", result.stderr)


if __name__ == "__main__":
    unittest.main()
