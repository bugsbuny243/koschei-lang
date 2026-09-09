"""Private Railway origin for a signed, source-free Koschei Lang package.

This process is not a customer application. It signs a pre-smoked staging release
at container startup, archives it, and serves the package only to callers holding
the shared artifact-origin bearer token. Neither the signing private key nor the
release public trust anchor is copied into the ZIP. The manifest carries only the
signer key id; the authoritative public key must be published independently.
"""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path("/app")
STAGING = ROOT / "release-staging"
PACKAGE = ROOT / "runtime" / "koschei-lang-0.10.0-testnet-linux-x86_64.zip"
METADATA = ROOT / "runtime" / "package.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare() -> None:
    token = os.environ.get("ARTIFACT_ORIGIN_TOKEN", "").strip()
    signing_key = os.environ.get("KOSCHEI_RELEASE_SIGNING_KEY_PEM", "").strip()
    if not token:
        raise SystemExit("ARTIFACT_ORIGIN_TOKEN is required")
    if not signing_key:
        raise SystemExit("KOSCHEI_RELEASE_SIGNING_KEY_PEM is required")
    if not STAGING.is_dir():
        raise SystemExit("sealed staging release is missing")

    runtime = ROOT / "runtime"
    release = runtime / "release"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    shutil.copytree(STAGING, release)

    with tempfile.TemporaryDirectory(prefix="koschei-release-key-") as tmp:
        key = Path(tmp) / "release-ed25519.pem"
        key.write_text(signing_key + "\n", encoding="utf-8")
        key.chmod(0o600)
        subprocess.run(
            ["python", str(ROOT / "tools" / "sign_solohost_release_v1.py"), str(release), "--private-key", str(key)],
            check=True,
        )

    # Deliberately do NOT derive/copy koschei-release-public.pem into ``release``.
    # A key learned only from the same ZIP cannot authenticate that ZIP. The
    # production owner public key/fingerprint belongs on an independent official
    # trust channel and is supplied separately to the publication verifier.
    bundled_public_key = release / "koschei-release-public.pem"
    if bundled_public_key.exists():
        bundled_public_key.unlink()

    notice = release / "TESTNET-NOTICE.txt"
    notice.write_text(
        "Koschei Lang Testnet sealed release. This package is for licensed Testnet validation and is not a Mainnet production release.\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(PACKAGE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(release.rglob("*")):
            if path.is_file():
                archive.write(path, Path("koschei-lang") / path.relative_to(release))

    manifest = json.loads((release / "koschei-release-manifest.json").read_text(encoding="utf-8"))
    metadata = {
        "ready": True,
        "product": "koschei-lang",
        "channel": "pi-testnet",
        "version": manifest.get("version"),
        "platform": manifest.get("platform"),
        "filename": PACKAGE.name,
        "sha256": sha256(PACKAGE),
        "size_bytes": PACKAGE.stat().st_size,
        "key_id": (manifest.get("signature") or {}).get("key_id"),
        "trust_anchor": "OUT_OF_BAND_REQUIRED",
    }
    METADATA.write_text(json.dumps(metadata, separators=(",", ":")) + "\n", encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "KoscheiArtifactOrigin/1"

    def _authorized(self) -> bool:
        expected = os.environ.get("ARTIFACT_ORIGIN_TOKEN", "").strip()
        return bool(expected) and self.headers.get("Authorization", "") == "Bearer " + expected

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if not self._authorized():
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/metadata":
            payload = METADATA.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/artifact":
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{PACKAGE.name}"')
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Content-Length", str(PACKAGE.stat().st_size))
            self.end_headers()
            with PACKAGE.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print("artifact-origin:", format % args, flush=True)


def main() -> None:
    prepare()
    port = int(os.environ.get("PORT", "8081"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
