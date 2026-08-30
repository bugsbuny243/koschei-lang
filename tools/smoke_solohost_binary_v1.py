"""Release smoke gate for a sealed Koschei SoloHost customer executable.

The gate proves that the compiled CLI still performs ordinary language work and
still enforces the capability-security rejection used in the supply-chain demo.
With --require-native-build it also proves that the packaged environment exposes
a usable Go toolchain for `ks build`.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HELLO = ROOT / "examples" / "hello.ks"
SUPPLY_CHAIN = ROOT / "examples" / "supply_chain" / "main.ks"


class SoloHostSmokeError(ValueError):
    pass


def _run(binary: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(binary), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SoloHostSmokeError(f"cannot execute sealed Koschei binary: {exc}") from exc


def _expect_success(binary: Path, label: str, args: list[str]) -> None:
    result = _run(binary, args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SoloHostSmokeError(f"{label} failed with exit {result.returncode}: {detail}")


def smoke(binary: Path, *, require_native_build: bool) -> None:
    binary = binary.resolve()
    if not binary.is_file():
        raise SoloHostSmokeError(f"sealed binary does not exist: {binary}")
    if not HELLO.is_file() or not SUPPLY_CHAIN.is_file():
        raise SoloHostSmokeError("repository smoke fixtures are missing")

    _expect_success(binary, "ks version", ["version"])
    _expect_success(binary, "ks check", ["check", str(HELLO)])
    _expect_success(binary, "ks run", ["run", str(HELLO)])
    _expect_success(binary, "ks caps", ["caps", str(HELLO)])

    denied = _run(binary, ["check", str(SUPPLY_CHAIN)])
    combined = (denied.stdout or "") + "\n" + (denied.stderr or "")
    if denied.returncode == 0:
        raise SoloHostSmokeError("supply-chain capability attack unexpectedly compiled successfully")
    if "KS2401" not in combined:
        raise SoloHostSmokeError(
            "supply-chain attack was rejected, but expected KS2401 capability denial was not preserved"
        )

    if require_native_build:
        if shutil.which("go") is None:
            raise SoloHostSmokeError("--require-native-build requires Go in the release/container environment")
        with tempfile.TemporaryDirectory(prefix="koschei-solohost-smoke-") as tmp:
            target = Path(tmp) / ("hello.exe" if sys.platform == "win32" else "hello")
            _expect_success(binary, "ks build", ["build", str(HELLO), "-o", str(target)])
            if not target.is_file():
                raise SoloHostSmokeError("ks build returned success but produced no native artifact")
            try:
                native = subprocess.run(
                    [str(target)],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except OSError as exc:
                raise SoloHostSmokeError(f"cannot execute Koschei native smoke artifact: {exc}") from exc
            if native.returncode != 0:
                detail = (native.stderr or native.stdout).strip()
                raise SoloHostSmokeError(f"native artifact failed with exit {native.returncode}: {detail}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument(
        "--require-native-build",
        action="store_true",
        help="also require Go-backed `ks build` and execute the resulting native program",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        smoke(args.binary, require_native_build=args.require_native_build)
    except SoloHostSmokeError as exc:
        print(f"SOLOHOST BINARY SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("KOSCHEI SOLOHOST BINARY SMOKE: PASS")
    print("checks: version, check, run, caps, KS2401 capability denial")
    if args.require_native_build:
        print("native build: PASS")
    else:
        print("native build: NOT REQUIRED IN THIS RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
