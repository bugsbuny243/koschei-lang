"""Assemble a source-free Koschei SoloHost staging artifact from a prebuilt executable.

This tool does not compile Koschei and does not sign releases. It creates a deterministic
staging directory containing only the customer executable and a digest-bound manifest.
Publication remains fail-closed until the manifest is signed by the owner-controlled
release process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys


MANIFEST_NAME = "koschei-release-manifest.json"
SCHEMA = "koschei.solohost-release-manifest/v1"


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


def assemble(*, binary: Path, output: Path, version: str, platform: str, source_commit: str | None) -> Path:
    binary = binary.resolve()
    output = output.resolve()
    version = _require_version(version)
    platform = platform.strip()
    if not platform:
        raise ValueError("platform must not be empty")
    if not binary.is_file():
        raise ValueError(f"binary does not exist: {binary}")
    if binary.suffix.lower() in {".py", ".pyi", ".pyc"}:
        raise ValueError("staging input must be a built executable, not Python source/bytecode")

    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    executable_name = "ks.exe" if binary.suffix.lower() == ".exe" else "ks"
    destination = output / executable_name
    shutil.copy2(binary, destination)
    if executable_name == "ks":
        mode = destination.stat().st_mode
        destination.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    manifest = {
        "schema": SCHEMA,
        "product": "koschei-lang",
        "channel": "pi-solohost",
        "version": version,
        "platform": platform,
        "source_commit": source_commit or "UNRECORDED",
        "entrypoint": executable_name,
        "artifact": {
            "path": executable_name,
            "sha256": _sha256(destination),
            "size_bytes": destination.stat().st_size,
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
    parser.add_argument("--source-commit", default=None)
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
        )
    except (OSError, ValueError) as exc:
        print(f"SOLOHOST STAGING ERROR: {exc}", file=sys.stderr)
        return 2

    print("KOSCHEI SOLOHOST STAGING: ASSEMBLED")
    print(f"manifest: {manifest_path}")
    print("publication status: BLOCKED UNTIL SIGNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
