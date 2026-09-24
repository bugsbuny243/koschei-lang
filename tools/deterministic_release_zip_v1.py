#!/usr/bin/env python3
"""Build a deterministic ZIP archive from one staged release directory."""
from __future__ import annotations

import argparse
from pathlib import Path
import stat
import zipfile

FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class DeterministicZipError(ValueError):
    pass


def _entries(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise DeterministicZipError(f"release staging directory is missing: {root}")
    return tuple(sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(root).as_posix()))


def build_archive(staging: Path, output: Path) -> None:
    staging = staging.resolve()
    output = output.resolve()
    entries = _entries(staging)
    if not entries:
        raise DeterministicZipError("release staging directory contains no files")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise DeterministicZipError(f"output archive already exists: {output}")

    with zipfile.ZipFile(
        output,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path in entries:
            relative = path.relative_to(staging).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            executable = bool(path.stat().st_mode & stat.S_IXUSR)
            mode = 0o755 if executable else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.flag_bits |= 0x800
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        build_archive(args.staging, args.output)
    except (OSError, DeterministicZipError) as exc:
        raise SystemExit(f"deterministic release zip refused: {exc}") from exc
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
