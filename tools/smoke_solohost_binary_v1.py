"""Release smoke gate for a sealed Koschei SoloHost customer executable.

The gate proves that the compiled CLI still performs ordinary language work and
still enforces the capability-security rejection used in the supply-chain demo.
It can emit a digest-bound smoke receipt for the staging assembler. A full
SoloHost release receipt requires Go-backed `ks build` validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
HELLO = ROOT / "examples" / "hello.ks"
SUPPLY_CHAIN = ROOT / "examples" / "supply_chain" / "main.ks"
RECEIPT_SCHEMA = "koschei.solohost-binary-smoke-receipt/v1"


class SoloHostSmokeError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(
    binary: Path,
    args: list[str],
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    runtime_env = os.environ.copy()
    if env_overrides:
        runtime_env.update(env_overrides)
    try:
        return subprocess.run(
            [str(binary), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=runtime_env,
        )
    except OSError as exc:
        raise SoloHostSmokeError(f"cannot execute sealed Koschei binary: {exc}") from exc


def _expect_success(
    binary: Path,
    label: str,
    args: list[str],
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = _run(binary, args, env_overrides=env_overrides)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SoloHostSmokeError(f"{label} failed with exit {result.returncode}: {detail}")
    return result


def _read_version(binary: Path) -> str:
    result = _expect_success(binary, "ks version --json", ["version", "--json"])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SoloHostSmokeError(f"ks version --json returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("name") != "koschei-lang":
        raise SoloHostSmokeError("ks version --json returned unexpected product identity")
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SoloHostSmokeError("ks version --json returned an empty version")
    return version.strip()


def _go_version() -> str:
    go_binary = shutil.which("go")
    if go_binary is None:
        raise SoloHostSmokeError("full SoloHost smoke requires Go in the release/container environment")
    try:
        result = subprocess.run(
            [go_binary, "version"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SoloHostSmokeError(f"cannot execute Go toolchain: {exc}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or result.stdout).strip()
        raise SoloHostSmokeError(f"cannot read Go toolchain identity: {detail}")
    return result.stdout.strip()


def smoke(binary: Path, *, require_native_build: bool) -> dict[str, object]:
    binary = binary.resolve()
    if not binary.is_file():
        raise SoloHostSmokeError(f"sealed binary does not exist: {binary}")
    if not HELLO.is_file() or not SUPPLY_CHAIN.is_file():
        raise SoloHostSmokeError("repository smoke fixtures are missing")

    started = int(time.time())
    version = _read_version(binary)
    _expect_success(binary, "ks check", ["check", str(HELLO)])
    _expect_success(binary, "ks run", ["run", str(HELLO)])
    _expect_success(binary, "ks caps", ["caps", str(HELLO)])

    # Customer shells and minimal containers are not guaranteed to expose a
    # UTF-8 locale. The sealed distribution entry point must therefore make
    # its Unicode CLI output portable even when Python would otherwise choose
    # ASCII for stdout/stderr.
    _expect_success(
        binary,
        "ks caps under C/ASCII locale",
        ["caps", str(HELLO)],
        env_overrides={
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONUTF8": "0",
            "PYTHONIOENCODING": "ascii",
        },
    )

    denied = _run(binary, ["check", str(SUPPLY_CHAIN)])
    combined = (denied.stdout or "") + "\n" + (denied.stderr or "")
    if denied.returncode == 0:
        raise SoloHostSmokeError("supply-chain capability attack unexpectedly compiled successfully")
    if "KS2401" not in combined:
        raise SoloHostSmokeError(
            "supply-chain attack was rejected, but expected KS2401 capability denial was not preserved"
        )

    native_passed = False
    go_identity: str | None = None
    if require_native_build:
        go_identity = _go_version()
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
            native_passed = True

    return {
        "schema": RECEIPT_SCHEMA,
        "product": "koschei-lang",
        "channel": "pi-solohost",
        "version": version,
        "binary": {
            "sha256": _sha256(binary),
            "size_bytes": binary.stat().st_size,
        },
        "checks": {
            "version_json": True,
            "check": True,
            "run": True,
            "caps": True,
            "caps_c_ascii_locale": True,
            "ks2401_supply_chain_denial": True,
        },
        "native_build": {
            "required": require_native_build,
            "passed": native_passed,
            "go_version": go_identity,
        },
        "started_unix": started,
        "finished_unix": int(time.time()),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument(
        "--require-native-build",
        action="store_true",
        help="also require Go-backed `ks build` and execute the resulting native program",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="write a digest-bound JSON smoke receipt for the staging assembler",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = smoke(args.binary, require_native_build=args.require_native_build)
        if args.receipt is not None:
            receipt_path = args.receipt.resolve()
            if receipt_path.exists():
                raise SoloHostSmokeError(f"smoke receipt already exists: {receipt_path}")
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, SoloHostSmokeError) as exc:
        print(f"SOLOHOST BINARY SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("KOSCHEI SOLOHOST BINARY SMOKE: PASS")
    print(f"version: {receipt['version']}")
    print("checks: version, check, run, caps, C-locale caps, KS2401 capability denial")
    if args.require_native_build:
        print("native build: PASS")
    else:
        print("native build: NOT REQUIRED IN THIS RUN")
    if args.receipt is not None:
        print(f"receipt: {args.receipt.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
