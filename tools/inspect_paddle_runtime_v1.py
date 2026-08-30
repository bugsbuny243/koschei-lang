"""Measure Linux runtime requirements for a Koschei Paddle release binary.

For dynamically linked ELF releases this records DT_NEEDED entries and derives
the highest referenced GLIBC symbol version from the exact binary. It does not
guess compatibility.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

SCHEMA = "koschei.runtime-requirements/v1"
GLIBC_RE = re.compile(r"\bGLIBC_(\d+)\.(\d+)(?:\.(\d+))?\b")
NEEDED_RE = re.compile(r"\(NEEDED\).*\[([^\]]+)\]")
INTERP_RE = re.compile(r"Requesting program interpreter:\s*([^\]]+)")


class RuntimeInspectionError(ValueError):
    pass


def _run(tool: str, args: list[str]) -> str:
    binary = shutil.which(tool)
    if binary is None:
        raise RuntimeInspectionError(f"{tool} is required for Linux runtime inspection")
    try:
        result = subprocess.run([binary, *args], check=False, capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeInspectionError(f"cannot execute {tool}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeInspectionError(f"{tool} failed: {detail}")
    return result.stdout


def _architecture(file_output: str) -> str:
    lowered = file_output.lower()
    if "x86-64" in lowered or "x86_64" in lowered:
        return "x86_64"
    if "aarch64" in lowered or "arm64" in lowered:
        return "aarch64"
    raise RuntimeInspectionError(f"unsupported/unknown ELF architecture: {file_output.strip()}")


def _max_glibc(version_info: str) -> str | None:
    versions: set[tuple[int, int, int]] = set()
    for major, minor, patch in GLIBC_RE.findall(version_info):
        versions.add((int(major), int(minor), int(patch or 0)))
    if not versions:
        return None
    major, minor, patch = max(versions)
    return f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"


def inspect(binary: Path, platform: str) -> dict[str, object]:
    binary = binary.resolve()
    if not binary.is_file():
        raise RuntimeInspectionError(f"release binary does not exist: {binary}")
    kind = _run("file", ["-b", str(binary)])
    if "ELF" not in kind:
        raise RuntimeInspectionError("this v1 inspector accepts Linux ELF binaries only")
    arch = _architecture(kind)
    dynamic = _run("readelf", ["-d", str(binary)])
    deps = sorted(set(NEEDED_RE.findall(dynamic)))
    program_headers = _run("readelf", ["-l", str(binary)])
    match = INTERP_RE.search(program_headers)
    interpreter = match.group(1).strip() if match else None

    if not deps and interpreter is None:
        libc = "none"
        minimum = None
    elif interpreter and "musl" in interpreter.lower():
        libc = "musl"
        minimum = None
    else:
        libc = "glibc"
        version_info = _run("readelf", ["--version-info", str(binary)])
        minimum = _max_glibc(version_info)
        if minimum is None:
            raise RuntimeInspectionError("dynamic glibc ELF has no measurable GLIBC symbol version; do not guess a minimum")

    return {
        "schema": SCHEMA,
        "product": "koschei-lang",
        "platform": platform,
        "architecture": arch,
        "os": "linux",
        "libc": libc,
        "minimum_libc_version": minimum,
        "dynamic_dependencies": deps,
        "program_interpreter": interpreter,
        "measurement": {
            "file": kind.strip(),
            "method": "readelf-dynamic+program-headers+version-info",
            "status": "MEASURED_FROM_EXACT_RELEASE_BINARY",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        data = inspect(args.binary, args.platform)
        target = args.output.resolve()
        if target.exists():
            raise RuntimeInspectionError(f"output already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, RuntimeInspectionError) as exc:
        print(f"KOSCHEI PADDLE RUNTIME INSPECTION ERROR: {exc}", file=sys.stderr)
        return 1
    print("KOSCHEI PADDLE RUNTIME REQUIREMENTS: MEASURED")
    print(f"platform: {data['platform']}")
    print(f"libc: {data['libc']}")
    print(f"minimum_libc_version: {data['minimum_libc_version']}")
    print(f"output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
