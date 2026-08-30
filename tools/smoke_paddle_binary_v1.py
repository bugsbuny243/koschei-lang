"""Functional/security smoke gate for a Paddle production Koschei binary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HELLO = ROOT / "examples" / "hello.ks"
SUPPLY_CHAIN = ROOT / "examples" / "supply_chain" / "main.ks"
SCHEMA = "koschei.paddle-binary-smoke-receipt/v1"
CHANNEL = "paddle-production"


class PaddleSmokeError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(binary: Path, args: list[str], *, cwd: Path | None = None, env_overrides: dict[str, str] | None = None, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    try:
        return subprocess.run([str(binary), *args], cwd=cwd or ROOT, check=False, capture_output=True, text=True, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PaddleSmokeError(f"cannot execute sealed Koschei binary: {exc}") from exc


def _success(binary: Path, label: str, args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    result = _run(binary, args, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PaddleSmokeError(f"{label} failed with exit {result.returncode}: {detail}")
    return result


def _version(binary: Path) -> str:
    result = _success(binary, "ks version --json", ["version", "--json"])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PaddleSmokeError("ks version --json returned invalid JSON") from exc
    if not isinstance(data, dict) or data.get("name") != "koschei-lang":
        raise PaddleSmokeError("ks version --json product identity mismatch")
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PaddleSmokeError("ks version --json returned empty version")
    return version.strip()


def smoke(binary: Path) -> dict[str, object]:
    binary = binary.resolve()
    if not binary.is_file():
        raise PaddleSmokeError(f"sealed binary does not exist: {binary}")
    if not HELLO.is_file() or not SUPPLY_CHAIN.is_file():
        raise PaddleSmokeError("repository smoke fixtures are missing")

    started = int(time.time())
    version = _version(binary)
    _success(binary, "ks check", ["check", str(HELLO)])
    _success(binary, "ks run", ["run", str(HELLO)])
    _success(binary, "ks caps", ["caps", str(HELLO)])
    _success(binary, "ks fmt", ["fmt", "--check", str(HELLO)])
    _success(binary, "ks lsp command", ["lsp", "--help"])
    _success(binary, "ks caps under C/ASCII locale", ["caps", str(HELLO)], env_overrides={"LANG": "C", "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONIOENCODING": "ascii"})

    denied = _run(binary, ["check", str(SUPPLY_CHAIN)])
    combined = (denied.stdout or "") + "\n" + (denied.stderr or "")
    if denied.returncode == 0:
        raise PaddleSmokeError("unauthorized supply-chain fixture unexpectedly compiled")
    if "KS2401" not in combined:
        raise PaddleSmokeError("unauthorized fixture was rejected without expected KS2401")

    with tempfile.TemporaryDirectory(prefix="koschei-paddle-new-") as tmp:
        destination = Path(tmp) / "demo"
        _success(binary, "ks new", ["new", "demo", "--path", str(destination)])
        if not destination.is_dir():
            raise PaddleSmokeError("ks new returned success but created no project")
        candidates = list(destination.rglob("*.ks"))
        if not candidates:
            raise PaddleSmokeError("ks new project contains no .ks entry source")
        _success(binary, "ks check generated project", ["check", str(candidates[0])])

    return {
        "schema": SCHEMA,
        "product": "koschei-lang",
        "channel": CHANNEL,
        "version": version,
        "binary": {"sha256": _sha256(binary), "size_bytes": binary.stat().st_size},
        "checks": {
            "version_json": True,
            "check": True,
            "run": True,
            "new": True,
            "caps": True,
            "fmt": True,
            "lsp_command": True,
            "caps_c_ascii_locale": True,
            "ks2401_supply_chain_denial": True,
        },
        "started_unix": started,
        "finished_unix": int(time.time()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = smoke(args.binary)
        receipt_path = args.receipt.resolve()
        if receipt_path.exists():
            raise PaddleSmokeError(f"receipt already exists: {receipt_path}")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, PaddleSmokeError) as exc:
        print(f"KOSCHEI PADDLE BINARY SMOKE ERROR: {exc}", file=__import__('sys').stderr)
        return 1
    print("KOSCHEI PADDLE BINARY SMOKE: PASS")
    print(f"version: {receipt['version']}")
    print("checks: version, check, run, new, caps, fmt, lsp, C-locale caps, KS2401 denial")
    print(f"receipt: {args.receipt.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
