"""Assemble a source-free Koschei SoloHost staging artifact from a proven executable.

The assembler accepts only a prebuilt executable whose exact bytes are bound to a
full functional/security smoke receipt. It does not compile Koschei and does not
sign releases. Publication remains fail-closed until the resulting manifest is
signed by the owner-controlled release process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import sys


MANIFEST_NAME = "koschei-release-manifest.json"
SCHEMA = "koschei.solohost-release-manifest/v1"
SMOKE_SCHEMA = "koschei.solohost-binary-smoke-receipt/v1"
SOURCE_COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
REQUIRED_SMOKE_CHECKS = {
    "version_json",
    "check",
    "run",
    "caps",
    "ks2401_supply_chain_denial",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_version(value: str) -> str:
    value = value.strip()
    if not value or any(ch.isspace() for ch in value):
        raise ValueError("version must be a non-empty token without whitespace")
    return value


def _require_source_commit(value: str) -> str:
    normalized = value.strip().lower()
    if not SOURCE_COMMIT_RE.fullmatch(normalized):
        raise ValueError("source commit must be a full 40- or 64-character hexadecimal commit id")
    return normalized


def _load_smoke_receipt(*, path: Path, binary: Path, version: str) -> dict[str, object]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"smoke receipt does not exist: {path}")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"smoke receipt is not valid JSON: {exc}") from exc
    if not isinstance(receipt, dict) or receipt.get("schema") != SMOKE_SCHEMA:
        raise ValueError("unexpected SoloHost smoke receipt schema")
    if receipt.get("product") != "koschei-lang" or receipt.get("channel") != "pi-solohost":
        raise ValueError("smoke receipt product/channel identity mismatch")
    if receipt.get("version") != version:
        raise ValueError(
            f"release version {version!r} does not match smoked binary version {receipt.get('version')!r}"
        )

    binary_info = receipt.get("binary")
    if not isinstance(binary_info, dict):
        raise ValueError("smoke receipt binary section is missing")
    if binary_info.get("sha256") != _sha256(binary):
        raise ValueError("smoke receipt SHA-256 does not match staging binary")
    if binary_info.get("size_bytes") != binary.stat().st_size:
        raise ValueError("smoke receipt size does not match staging binary")

    checks = receipt.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("smoke receipt checks section is missing")
    missing = sorted(name for name in REQUIRED_SMOKE_CHECKS if checks.get(name) is not True)
    if missing:
        raise ValueError("smoke receipt is missing required passing checks: " + ", ".join(missing))

    native = receipt.get("native_build")
    if not isinstance(native, dict):
        raise ValueError("smoke receipt native_build section is missing")
    if native.get("required") is not True or native.get("passed") is not True:
        raise ValueError("SoloHost customer staging requires a passing required native-build smoke")
    go_version = native.get("go_version")
    if not isinstance(go_version, str) or not go_version.strip():
        raise ValueError("full native-build smoke must record the Go toolchain identity")
    return receipt


def assemble(
    *,
    binary: Path,
    output: Path,
    version: str,
    platform: str,
    source_commit: str,
    smoke_receipt: Path,
) -> Path:
    binary = binary.resolve()
    output = output.resolve()
    version = _require_version(version)
    source_commit = _require_source_commit(source_commit)
    platform = platform.strip()
    if not platform:
        raise ValueError("platform must not be empty")
    if not binary.is_file():
        raise ValueError(f"binary does not exist: {binary}")
    if binary.suffix.lower() in {".py", ".pyi", ".pyc", ".go"}:
        raise ValueError("staging input must be a built executable, not source/bytecode")

    receipt = _load_smoke_receipt(path=smoke_receipt, binary=binary, version=version)
    smoke_receipt = smoke_receipt.resolve()

    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    executable_name = "ks.exe" if binary.suffix.lower() == ".exe" else "ks"
    destination = output / executable_name
    shutil.copy2(binary, destination)
    if executable_name == "ks":
        mode = destination.stat().st_mode
        destination.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    native = receipt["native_build"]
    assert isinstance(native, dict)
    manifest = {
        "schema": SCHEMA,
        "product": "koschei-lang",
        "channel": "pi-solohost",
        "version": version,
        "platform": platform,
        "source_commit": source_commit,
        "entrypoint": executable_name,
        "artifact": {
            "path": executable_name,
            "sha256": _sha256(destination),
            "size_bytes": destination.stat().st_size,
        },
        "release_evidence": {
            "smoke_receipt_schema": SMOKE_SCHEMA,
            "smoke_receipt_sha256": _sha256(smoke_receipt),
            "native_build_passed": True,
            "go_version": native["go_version"],
        },
        "commercial": {
            "billing_mode": "one_time_pi",
            "recurring_subscription": False,
        },
        "signature": {
            "status": "UNSIGNED-STAGING",
            "scheme": None,
            "key_id": None,
            "signature_file": None,
        },
    }
    manifest_path = output / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True, help="release target, e.g. linux-x86_64")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--smoke-receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest_path = assemble(
            binary=args.binary,
            output=args.output,
            version=args.version,
            platform=args.platform,
            source_commit=args.source_commit,
            smoke_receipt=args.smoke_receipt,
        )
    except (OSError, ValueError) as exc:
        print(f"SOLOHOST STAGING ERROR: {exc}", file=sys.stderr)
        return 2

    print("KOSCHEI SOLOHOST STAGING: ASSEMBLED")
    print(f"manifest: {manifest_path}")
    print("evidence: binary bytes match full native-build smoke receipt")
    print("publication status: BLOCKED UNTIL SIGNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
