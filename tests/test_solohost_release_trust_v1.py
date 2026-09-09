from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.sign_solohost_release_v1 import sign_release
from tools.verify_solohost_artifact_v1 import verify_artifact


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required for Ed25519 release tests")
class SoloHostReleaseTrustTests(unittest.TestCase):
    def _keypair(self, directory: Path, name: str) -> tuple[Path, Path]:
        private_key = directory / f"{name}-private.pem"
        public_key = directory / f"{name}-public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(private_key),
                "-pubout",
                "-out",
                str(public_key),
            ],
            check=True,
            capture_output=True,
        )
        return private_key, public_key

    def _artifact(self, base: Path, payload: bytes = b"sealed-koschei-binary\n") -> Path:
        root = base / "artifact"
        root.mkdir()
        binary = root / "ks"
        binary.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        manifest = {
            "schema": "koschei.solohost-release-manifest/v1",
            "product": "koschei-lang",
            "channel": "pi-solohost",
            "version": "0.10.0",
            "platform": "linux-x86_64",
            "source_commit": "0" * 40,
            "entrypoint": "ks",
            "artifact": {
                "path": "ks",
                "sha256": digest,
                "size_bytes": len(payload),
            },
            "signature": {
                "status": "UNSIGNED-STAGING",
                "scheme": None,
                "key_id": None,
                "signature_file": None,
            },
        }
        (root / "koschei-release-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return root

    def test_signed_artifact_passes_with_independently_supplied_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            artifact = self._artifact(base)
            private_key, public_key = self._keypair(base, "owner")
            sign_release(artifact, private_key)

            self.assertEqual(
                verify_artifact(artifact, trusted_public_key=public_key),
                [],
            )

    def test_artifact_bundled_or_attacker_key_cannot_replace_pinned_trust(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            artifact = self._artifact(base)
            attacker_private, attacker_public = self._keypair(base, "attacker")
            _, owner_public = self._keypair(base, "owner")
            sign_release(artifact, attacker_private)
            # Even if the attacker ships their public key beside the artifact,
            # publication trust comes from owner_public supplied out-of-band.
            (artifact / "koschei-release-public.pem").write_bytes(attacker_public.read_bytes())

            failures = verify_artifact(artifact, trusted_public_key=owner_public)

            self.assertTrue(
                any("does not match independently trusted key" in item for item in failures),
                failures,
            )

    def test_binary_tamper_after_signing_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            artifact = self._artifact(base)
            private_key, public_key = self._keypair(base, "owner")
            sign_release(artifact, private_key)
            (artifact / "ks").write_bytes(b"tampered\n")

            failures = verify_artifact(artifact, trusted_public_key=public_key)

            self.assertTrue(any("SHA-256 mismatch" in item for item in failures), failures)
            self.assertTrue(any("size mismatch" in item for item in failures), failures)

    def test_unsigned_staging_artifact_is_not_publishable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            artifact = self._artifact(base)
            _, public_key = self._keypair(base, "owner")

            failures = verify_artifact(artifact, trusted_public_key=public_key)

            self.assertTrue(any("not marked SIGNED" in item for item in failures), failures)
            self.assertTrue(any("signature scheme" in item for item in failures), failures)

    def test_no_external_trust_anchor_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            artifact = self._artifact(base)
            private_key, _ = self._keypair(base, "owner")
            sign_release(artifact, private_key)

            failures = verify_artifact(artifact)

            self.assertIn(
                "missing independent trusted public key; artifact-bundled keys are not trust anchors",
                failures,
            )


if __name__ == "__main__":
    unittest.main()
