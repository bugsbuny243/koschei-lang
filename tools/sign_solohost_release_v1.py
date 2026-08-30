"""Sign a Koschei SoloHost release manifest with an owner-held Ed25519 key.

The private key is supplied by path at release time and is never copied into the
artifact. The manifest records a key id derived from the normalized public key;
the detached signature covers the exact final manifest bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


MANIFEST_NAME = "koschei-release-manifest.json"
SIGNATURE_NAME = "koschei-release-manifest.sig"
SCHEME = "ed25519-openssl-raw-v1"
SCHEMA = "koschei.solohost-release-manifest/v1"


class ReleaseSigningError(ValueError):
    pass


def _run(command: list[str]) -> None:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise ReleaseSigningError(f"cannot execute OpenSSL: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseSigningError(f"OpenSSL command failed: {detail}")


def _public_key_identity(private_key: Path) -> tuple[str, bytes]:
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        public_pem = temp / "public.pem"
        public_der = temp / "public.der"
        _run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_pem)])
        _run([
            "openssl",
            "pkey",
            "-pubin",
            "-in",
            str(public_pem),
            "-outform",
            "DER",
            "-out",
            str(public_der),
        ])
        der = public_der.read_bytes()
        return "ed25519-sha256:" + hashlib.sha256(der).hexdigest(), public_pem.read_bytes()


def sign_release(artifact: Path, private_key: Path) -> str:
    artifact = artifact.resolve()
    private_key = private_key.resolve()
    if not artifact.is_dir():
        raise ReleaseSigningError(f"artifact directory does not exist: {artifact}")
    if not private_key.is_file():
        raise ReleaseSigningError(f"private key does not exist: {private_key}")
    if shutil.which("openssl") is None:
        raise ReleaseSigningError("openssl executable is required")

    manifest_path = artifact / MANIFEST_NAME
    signature_path = artifact / SIGNATURE_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseSigningError(f"cannot load release manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ReleaseSigningError("unexpected release manifest schema")

    key_id, public_pem = _public_key_identity(private_key)
    manifest["signature"] = {
        "status": "SIGNED",
        "scheme": SCHEME,
        "key_id": key_id,
        "signature_file": SIGNATURE_NAME,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _run([
        "openssl",
        "pkeyutl",
        "-sign",
        "-rawin",
        "-in",
        str(manifest_path),
        "-inkey",
        str(private_key),
        "-out",
        str(signature_path),
    ])

    with tempfile.TemporaryDirectory() as tmp:
        public_path = Path(tmp) / "release-public.pem"
        public_path.write_bytes(public_pem)
        _run([
            "openssl",
            "pkeyutl",
            "-verify",
            "-rawin",
            "-in",
            str(manifest_path),
            "-pubin",
            "-inkey",
            str(public_path),
            "-sigfile",
            str(signature_path),
        ])
    return key_id


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        key_id = sign_release(args.artifact_directory, args.private_key)
    except ReleaseSigningError as exc:
        print(f"SOLOHOST RELEASE SIGNING ERROR: {exc}", file=sys.stderr)
        return 2
    print("KOSCHEI SOLOHOST RELEASE: SIGNED")
    print(f"key_id: {key_id}")
    print(f"signature: {args.artifact_directory.resolve() / SIGNATURE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
