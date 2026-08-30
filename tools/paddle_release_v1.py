"""Production release gate for Koschei Lang sold through Paddle.

This tool is intentionally payment-provider adjacent, not part of language
semantics. It assembles, signs, and verifies a source-free customer artifact.
Paddle checkout/webhook handling lives outside the compiler process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MANIFEST_NAME = "koschei-paddle-release-manifest.json"
SIGNATURE_NAME = "koschei-paddle-release-manifest.sig"
RUNTIME_NAME = "RUNTIME-REQUIREMENTS.json"
CUSTOMER_README_NAME = "README.txt"
LICENSE_NAME = "LICENSE.txt"
SCHEMA = "koschei.paddle-release-manifest/v1"
SMOKE_SCHEMA = "koschei.paddle-binary-smoke-receipt/v1"
RUNTIME_SCHEMA = "koschei.runtime-requirements/v1"
CHANNEL = "paddle-production"
SIGNATURE_SCHEME = "ed25519-openssl-raw-v1"
KEY_ID_PREFIX = "ed25519-sha256:"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
EXECUTABLES = {"ks", "ks.exe"}
REQUIRED_SMOKE_CHECKS = {
    "version_json",
    "check",
    "run",
    "new",
    "caps",
    "fmt",
    "lsp_command",
    "caps_c_ascii_locale",
    "ks2401_supply_chain_denial",
}
FORBIDDEN_PATH_PARTS = {".git", ".github", "tests", "fixtures", "bench", "benchmarks", "__pycache__"}
FORBIDDEN_SUFFIXES = {".py", ".pyi", ".pyc", ".go"}
FORBIDDEN_NAMES = {
    "TESTNET-NOTICE.txt",
    "koschei-release-public.pem",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
}
SECRET_MARKERS = {
    "private_key",
    "signing_key",
    "webhook_secret",
    "api_key",
    "access_token",
    "client_secret",
    "wallet_seed",
    "mnemonic",
    ".key",
}


class PaddleReleaseError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PaddleReleaseError(f"{label} does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleReleaseError(f"cannot load {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise PaddleReleaseError(f"{label} must be a JSON object")
    return data


def _require_token(value: str, *, label: str) -> str:
    value = value.strip()
    if not value or any(ch.isspace() for ch in value):
        raise PaddleReleaseError(f"{label} must be a non-empty token without whitespace")
    return value


def _require_commit(value: str) -> str:
    value = value.strip().lower()
    if COMMIT_RE.fullmatch(value) is None:
        raise PaddleReleaseError("source commit must be a full 40- or 64-character lowercase hex id")
    return value


def _simple_name(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PaddleReleaseError(f"{field} must be a non-empty filename")
    p = Path(value)
    if p.name != value or "/" in value or "\\" in value or value in {".", ".."}:
        raise PaddleReleaseError(f"{field} must be a simple artifact-local filename")
    return value


def _run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, check=False, capture_output=True)
    except OSError as exc:
        raise PaddleReleaseError(f"cannot execute external verifier: {exc}") from exc


def _require_openssl() -> str:
    openssl = shutil.which("openssl")
    if openssl is None:
        raise PaddleReleaseError("openssl is required for Ed25519 release signing/verification")
    return openssl


def _public_key_id_from_private(private_key: Path) -> str:
    openssl = _require_openssl()
    with tempfile.TemporaryDirectory(prefix="koschei-paddle-keyid-") as tmp:
        der = Path(tmp) / "public.der"
        result = _run([
            openssl, "pkey", "-in", str(private_key), "-pubout",
            "-outform", "DER", "-out", str(der),
        ])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            raise PaddleReleaseError(f"invalid Ed25519 private key: {detail}")
        return KEY_ID_PREFIX + hashlib.sha256(der.read_bytes()).hexdigest()


def _public_key_id(trusted_public_key: Path) -> str:
    openssl = _require_openssl()
    with tempfile.TemporaryDirectory(prefix="koschei-paddle-trust-") as tmp:
        der = Path(tmp) / "public.der"
        result = _run([
            openssl, "pkey", "-pubin", "-in", str(trusted_public_key),
            "-outform", "DER", "-out", str(der),
        ])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            raise PaddleReleaseError(f"invalid trusted public key: {detail}")
        return KEY_ID_PREFIX + hashlib.sha256(der.read_bytes()).hexdigest()


def _validate_smoke(path: Path, binary: Path, version: str) -> dict[str, object]:
    receipt = _load_json(path, label="Paddle smoke receipt")
    if receipt.get("schema") != SMOKE_SCHEMA:
        raise PaddleReleaseError("unexpected Paddle smoke receipt schema")
    if receipt.get("product") != "koschei-lang" or receipt.get("channel") != CHANNEL:
        raise PaddleReleaseError("smoke receipt product/channel identity mismatch")
    if receipt.get("version") != version:
        raise PaddleReleaseError("smoke receipt version does not match release version")
    info = receipt.get("binary")
    if not isinstance(info, dict):
        raise PaddleReleaseError("smoke receipt binary section is missing")
    if info.get("sha256") != _sha256(binary) or info.get("size_bytes") != binary.stat().st_size:
        raise PaddleReleaseError("smoke receipt does not bind the exact release binary")
    checks = receipt.get("checks")
    if not isinstance(checks, dict):
        raise PaddleReleaseError("smoke receipt checks section is missing")
    missing = sorted(name for name in REQUIRED_SMOKE_CHECKS if checks.get(name) is not True)
    if missing:
        raise PaddleReleaseError("smoke receipt missing passing checks: " + ", ".join(missing))
    return receipt


def _validate_runtime(path: Path, platform: str) -> dict[str, object]:
    runtime = _load_json(path, label="runtime requirements")
    if runtime.get("schema") != RUNTIME_SCHEMA:
        raise PaddleReleaseError("unexpected runtime requirements schema")
    if runtime.get("product") != "koschei-lang" or runtime.get("platform") != platform:
        raise PaddleReleaseError("runtime requirements product/platform mismatch")
    for field in ("architecture", "os", "libc"):
        if not isinstance(runtime.get(field), str) or not str(runtime.get(field)).strip():
            raise PaddleReleaseError(f"runtime requirements {field} is required")
    deps = runtime.get("dynamic_dependencies")
    if not isinstance(deps, list) or not all(isinstance(item, str) and item.strip() for item in deps):
        raise PaddleReleaseError("runtime requirements dynamic_dependencies must be a string list")
    if runtime.get("libc") != "none":
        minimum = runtime.get("minimum_libc_version")
        if not isinstance(minimum, str) or not minimum.strip():
            raise PaddleReleaseError("runtime requirements minimum_libc_version is required")
    return runtime


def assemble(
    *,
    binary: Path,
    output: Path,
    version: str,
    platform: str,
    source_commit: str,
    smoke_receipt: Path,
    runtime_requirements: Path,
    customer_readme: Path,
    license_notice: Path,
) -> Path:
    binary = binary.resolve()
    output = output.resolve()
    version = _require_token(version, label="version")
    platform = _require_token(platform, label="platform")
    source_commit = _require_commit(source_commit)
    if not binary.is_file():
        raise PaddleReleaseError(f"binary does not exist: {binary}")
    if binary.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise PaddleReleaseError("release input must be an executable, not source")
    if output.exists() and any(output.iterdir()):
        raise PaddleReleaseError(f"output directory must be empty: {output}")
    for doc, label in ((customer_readme, "customer readme"), (license_notice, "license notice")):
        if not doc.is_file():
            raise PaddleReleaseError(f"{label} does not exist: {doc}")

    _validate_smoke(smoke_receipt.resolve(), binary, version)
    _validate_runtime(runtime_requirements.resolve(), platform)

    output.mkdir(parents=True, exist_ok=True)
    executable_name = "ks.exe" if binary.suffix.lower() == ".exe" else "ks"
    executable = output / executable_name
    shutil.copy2(binary, executable)
    if executable_name == "ks":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    shutil.copy2(runtime_requirements, output / RUNTIME_NAME)
    shutil.copy2(customer_readme, output / CUSTOMER_README_NAME)
    shutil.copy2(license_notice, output / LICENSE_NAME)

    manifest = {
        "schema": SCHEMA,
        "product": "koschei-lang",
        "channel": CHANNEL,
        "release_status": "PRODUCTION",
        "version": version,
        "platform": platform,
        "source_commit": source_commit,
        "entrypoint": executable_name,
        "artifact": {
            "path": executable_name,
            "sha256": _sha256(executable),
            "size_bytes": executable.stat().st_size,
        },
        "evidence": {
            "smoke_receipt_schema": SMOKE_SCHEMA,
            "smoke_receipt_sha256": _sha256(smoke_receipt.resolve()),
            "ks2401_supply_chain_denial": True,
            "runtime_requirements_file": RUNTIME_NAME,
            "runtime_requirements_sha256": _sha256(runtime_requirements.resolve()),
        },
        "commerce": {
            "provider": "paddle",
            "fulfillment": "external-entitlement-bound-download",
            "price_id": None,
            "transaction_id": None,
            "note": "Paddle transaction/customer identifiers are entitlement records, not release identity.",
        },
        "signature": {
            "status": "UNSIGNED-STAGING",
            "scheme": None,
            "key_id": None,
            "signature_file": None,
        },
    }
    path = output / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sign(artifact: Path, private_key: Path) -> str:
    artifact = artifact.resolve()
    private_key = private_key.resolve()
    if not artifact.is_dir():
        raise PaddleReleaseError(f"artifact directory does not exist: {artifact}")
    if not private_key.is_file():
        raise PaddleReleaseError(f"private key does not exist: {private_key}")
    manifest_path = artifact / MANIFEST_NAME
    manifest = _load_json(manifest_path, label="Paddle release manifest")
    if manifest.get("schema") != SCHEMA or manifest.get("channel") != CHANNEL:
        raise PaddleReleaseError("unexpected Paddle production release manifest")
    key_id = _public_key_id_from_private(private_key)
    manifest["signature"] = {
        "status": "SIGNED",
        "scheme": SIGNATURE_SCHEME,
        "key_id": key_id,
        "signature_file": SIGNATURE_NAME,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    openssl = _require_openssl()
    result = _run([
        openssl, "pkeyutl", "-sign", "-rawin", "-in", str(manifest_path),
        "-inkey", str(private_key), "-out", str(artifact / SIGNATURE_NAME),
    ])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise PaddleReleaseError(f"release signing failed: {detail}")
    return key_id


def verify(artifact: Path, trusted_public_key: Path) -> list[str]:
    artifact = artifact.resolve()
    trusted_public_key = trusted_public_key.resolve()
    failures: list[str] = []
    if not artifact.is_dir():
        return [f"artifact directory does not exist: {artifact}"]
    files = [p for p in artifact.rglob("*") if p.is_file()]
    if not files:
        return ["artifact directory is empty"]

    for path in files:
        rel = path.relative_to(artifact)
        lower = path.name.lower()
        blocked_parts = sorted(set(rel.parts) & FORBIDDEN_PATH_PARTS)
        if blocked_parts:
            failures.append(f"forbidden private/source path {blocked_parts!r}: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden source/build suffix {path.suffix}: {rel}")
        if path.name in FORBIDDEN_NAMES:
            failures.append(f"forbidden Paddle production file: {rel}")
        markers = sorted(m for m in SECRET_MARKERS if m in lower)
        if markers:
            failures.append(f"secret-like filename marker {markers!r}: {rel}")

    required = {MANIFEST_NAME, SIGNATURE_NAME, RUNTIME_NAME, CUSTOMER_README_NAME, LICENSE_NAME}
    missing_files = sorted(required - {p.name for p in files})
    if missing_files:
        failures.append("missing required customer files: " + ", ".join(missing_files))

    try:
        manifest = _load_json(artifact / MANIFEST_NAME, label="Paddle release manifest")
    except PaddleReleaseError as exc:
        return failures + [str(exc)]

    if manifest.get("schema") != SCHEMA:
        failures.append("unexpected Paddle release manifest schema")
    if manifest.get("product") != "koschei-lang":
        failures.append("manifest product identity mismatch")
    if manifest.get("channel") != CHANNEL or manifest.get("release_status") != "PRODUCTION":
        failures.append("manifest is not Paddle PRODUCTION channel")

    try:
        entrypoint = _simple_name(manifest.get("entrypoint"), field="entrypoint")
    except PaddleReleaseError as exc:
        failures.append(str(exc))
        entrypoint = ""
    if entrypoint and entrypoint not in EXECUTABLES:
        failures.append("manifest entrypoint is not ks/ks.exe")

    info = manifest.get("artifact")
    if not isinstance(info, dict):
        failures.append("manifest artifact section is missing")
        info = {}
    try:
        artifact_name = _simple_name(info.get("path"), field="artifact.path")
    except PaddleReleaseError as exc:
        failures.append(str(exc))
        artifact_name = ""
    if entrypoint and artifact_name and entrypoint != artifact_name:
        failures.append("manifest entrypoint and artifact.path differ")
    expected_sha = info.get("sha256")
    expected_size = info.get("size_bytes")
    target = artifact / artifact_name if artifact_name else None
    if not isinstance(expected_sha, str) or SHA256_RE.fullmatch(expected_sha) is None:
        failures.append("manifest artifact.sha256 is invalid")
    if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0:
        failures.append("manifest artifact.size_bytes is invalid")
    if target is None or not target.is_file():
        failures.append("manifest-bound executable is missing")
    else:
        if isinstance(expected_sha, str) and SHA256_RE.fullmatch(expected_sha) and _sha256(target) != expected_sha:
            failures.append("artifact SHA-256 mismatch")
        if isinstance(expected_size, int) and not isinstance(expected_size, bool) and expected_size >= 0 and target.stat().st_size != expected_size:
            failures.append("artifact size mismatch")

    evidence = manifest.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("ks2401_supply_chain_denial") is not True:
        failures.append("release evidence does not assert ks2401_supply_chain_denial=true")
    else:
        runtime_path = artifact / RUNTIME_NAME
        if runtime_path.is_file():
            digest = evidence.get("runtime_requirements_sha256")
            if not isinstance(digest, str) or digest != _sha256(runtime_path):
                failures.append("runtime requirements digest mismatch")
            try:
                _validate_runtime(runtime_path, str(manifest.get("platform", "")))
            except PaddleReleaseError as exc:
                failures.append(str(exc))

    signature = manifest.get("signature")
    if not isinstance(signature, dict):
        failures.append("manifest signature section is missing")
        signature = {}
    if signature.get("status") != "SIGNED":
        failures.append("release manifest is not SIGNED")
    if signature.get("scheme") != SIGNATURE_SCHEME:
        failures.append("unexpected release signature scheme")
    key_id = signature.get("key_id")
    if not isinstance(key_id, str) or not key_id.startswith(KEY_ID_PREFIX):
        failures.append("manifest signer key_id is invalid")
    if signature.get("signature_file") != SIGNATURE_NAME:
        failures.append("manifest signature file identity mismatch")

    try:
        trusted_id = _public_key_id(trusted_public_key)
    except PaddleReleaseError as exc:
        failures.append(str(exc))
        trusted_id = ""
    if trusted_id and key_id != trusted_id:
        failures.append("release signer does not match independently trusted public key")

    signature_path = artifact / SIGNATURE_NAME
    if trusted_id and key_id == trusted_id and signature_path.is_file():
        result = _run([
            _require_openssl(), "pkeyutl", "-verify", "-rawin",
            "-in", str(artifact / MANIFEST_NAME), "-pubin",
            "-inkey", str(trusted_public_key), "-sigfile", str(signature_path),
        ])
        if result.returncode != 0:
            failures.append("detached release signature verification failed")

    return failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    a = subs.add_parser("assemble", help="assemble unsigned Paddle production staging")
    a.add_argument("--binary", required=True, type=Path)
    a.add_argument("--output", required=True, type=Path)
    a.add_argument("--version", required=True)
    a.add_argument("--platform", required=True)
    a.add_argument("--source-commit", required=True)
    a.add_argument("--smoke-receipt", required=True, type=Path)
    a.add_argument("--runtime-requirements", required=True, type=Path)
    a.add_argument("--customer-readme", required=True, type=Path)
    a.add_argument("--license-notice", required=True, type=Path)

    s = subs.add_parser("sign", help="sign staging with an owner-held Ed25519 private key")
    s.add_argument("artifact_directory", type=Path)
    s.add_argument("--private-key", required=True, type=Path)

    v = subs.add_parser("verify", help="verify production artifact against external trust anchor")
    v.add_argument("artifact_directory", type=Path)
    v.add_argument("--trusted-public-key", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "assemble":
            path = assemble(
                binary=args.binary,
                output=args.output,
                version=args.version,
                platform=args.platform,
                source_commit=args.source_commit,
                smoke_receipt=args.smoke_receipt,
                runtime_requirements=args.runtime_requirements,
                customer_readme=args.customer_readme,
                license_notice=args.license_notice,
            )
            print("KOSCHEI PADDLE RELEASE: ASSEMBLED")
            print(f"manifest: {path}")
            print("publication status: BLOCKED UNTIL SIGNED AND EXTERNALLY VERIFIED")
            return 0
        if args.command == "sign":
            key_id = sign(args.artifact_directory, args.private_key)
            print("KOSCHEI PADDLE RELEASE: SIGNED")
            print(f"key_id: {key_id}")
            print("trust anchor: MUST BE PUBLISHED OUT OF BAND")
            return 0
        failures = verify(args.artifact_directory, args.trusted_public_key)
    except (OSError, PaddleReleaseError) as exc:
        print(f"KOSCHEI PADDLE RELEASE ERROR: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("KOSCHEI PADDLE RELEASE: REJECTED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("KOSCHEI PADDLE RELEASE: PASS")
    print("production channel, exact binary, external signer trust, runtime requirements: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
