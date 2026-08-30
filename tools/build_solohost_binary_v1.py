"""Owner-controlled Nuitka builder for the Koschei SoloHost customer executable.

This is bootstrap release tooling, not a Koschei language dependency. It compiles
only the narrow SoloHost entry point and deliberately does not include repository
source/data directories. In particular, `native/datajson/*.go` is not copied into
the customer distribution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "tools" / "solohost_binary_entry_v1.py"
RECEIPT_SCHEMA = "koschei.solohost-binary-build-receipt/v1"
EXECUTABLE_NAMES = {"ks", "ks.exe", "ks.bin"}


class SoloHostBinaryBuildError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise SoloHostBinaryBuildError(f"cannot execute build command: {exc}") from exc


def _nuitka_version() -> str:
    result = _run([sys.executable, "-m", "nuitka", "--version"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SoloHostBinaryBuildError(
            "Nuitka is required in the owner-controlled release environment; "
            f"`{sys.executable} -m nuitka --version` failed: {detail}"
        )
    first = (result.stdout or result.stderr).strip().splitlines()
    return first[0] if first else "unknown"


def _candidate_binaries(output: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for path in output.rglob("*")
        if path.is_file()
        and path.name in EXECUTABLE_NAMES
        and not any(part.endswith(".build") for part in path.parts)
    )


def build(*, mode: str, output: Path, extra_arg: list[str]) -> tuple[Path, Path]:
    if mode not in {"standalone", "onefile"}:
        raise SoloHostBinaryBuildError("mode must be standalone or onefile")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SoloHostBinaryBuildError(f"output directory must be empty: {output}")

    nuitka_version = _nuitka_version()
    command = [
        sys.executable,
        "-m",
        "nuitka",
        f"--mode={mode}",
        "--python-flag=isolated",
        f"--output-dir={output}",
        "--output-filename=ks",
        str(ENTRY),
    ]
    command.extend(extra_arg)

    started = time.time()
    result = _run(command)
    finished = time.time()
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SoloHostBinaryBuildError(f"Nuitka build failed: {detail}")

    candidates = _candidate_binaries(output)
    if len(candidates) != 1:
        rendered = ", ".join(str(path.relative_to(output)) for path in candidates) or "none"
        raise SoloHostBinaryBuildError(f"expected exactly one customer executable, found: {rendered}")
    binary = candidates[0]

    # Fail closed if the distributable tree itself contains obvious private source.
    customer_root = binary.parent if mode == "standalone" else output
    leaked = sorted(
        path.relative_to(customer_root)
        for path in customer_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".pyi", ".go"}
    )
    if leaked:
        preview = ", ".join(str(path) for path in leaked[:10])
        raise SoloHostBinaryBuildError(f"compiled customer output leaks source files: {preview}")

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "builder": "nuitka-bootstrap",
        "mode": mode,
        "python": sys.version.split()[0],
        "nuitka": nuitka_version,
        "entry": str(ENTRY.relative_to(ROOT)),
        "command": command,
        "started_unix": int(started),
        "finished_unix": int(finished),
        "executable": {
            "path": str(binary.relative_to(output)),
            "sha256": _sha256(binary),
            "size_bytes": binary.stat().st_size,
        },
        "source_data_policy": {
            "repository_data_dirs_included": False,
            "native_datajson_go_included": False,
        },
    }
    receipt_path = output / "koschei-solohost-build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return binary, receipt_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("standalone", "onefile"), default="standalone")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--nuitka-arg",
        action="append",
        default=[],
        help="additional owner-controlled Nuitka argument; may be repeated",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        binary, receipt = build(mode=args.mode, output=args.output, extra_arg=args.nuitka_arg)
    except SoloHostBinaryBuildError as exc:
        print(f"SOLOHOST BINARY BUILD ERROR: {exc}", file=sys.stderr)
        return 2
    print("KOSCHEI SOLOHOST BINARY: BUILT")
    print(f"mode: {args.mode}")
    print(f"binary: {binary}")
    print(f"receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
