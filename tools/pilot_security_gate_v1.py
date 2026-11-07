#!/usr/bin/env python3
"""Verify a trusted Koschei Lang customer ZIP as an isolated security *pilot*.

This is NOT production certification or a malware sandbox. The verified
SHA-256 must come from an independently trusted release channel: a hash
published beside an untrusted artifact cannot authenticate its origin.
The extracted Koschei code is executed only after exact hash verification;
run this gate on isolated CI infrastructure, not an everyday workstation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

SCHEMA = "koschei.customer-pilot-evidence/v1"
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
REQUIRED = frozenset({
    "LICENSE", "LICENSING.md", "README.md", "install.sh",
    "RELEASE_NOTES.md", "RELEASE_NOTES.tr.md",
    "pyproject.toml", "koschei/__main__.py",
    "koschei/core_library/secure.ks", "docs/reference/CORE_LIBRARY.md",
    "examples/hello.ks", "examples/supply_chain/main.ks",
    "examples/supply_chain/analytics.ks",
    "examples/apps/secretscan/main.ks", "examples/apps/integrity/main.ks",
})


class PilotGateError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_archive(archive_path: Path, expected_sha256: str) -> tuple[str, str]:
    """Check exact trusted hash, ZIP boundaries, mandatory product files."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise PilotGateError("expected_sha256 must be exactly 64 lowercase hex digits")
    data = archive_path.read_bytes()
    actual = _sha256(data)
    if actual != expected_sha256:
        raise PilotGateError("bundle digest differs from independently trusted SHA-256")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names: set[str] = set()
            roots: set[str] = set()
            total = 0
            relative: set[str] = set()
            for member in archive.infolist():
                name = member.filename
                parts = PurePosixPath(name).parts
                if (
                    name in names or not parts or name.startswith("/")
                    or "\\" in name or ".." in parts or "." in parts
                    or member.is_dir() or len(parts) < 2
                    or member.file_size > MAX_MEMBER_BYTES
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise PilotGateError("invalid or unsafe ZIP member")
                names.add(name)
                roots.add(parts[0])
                relative.add("/".join(parts[1:]))
                total += member.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise PilotGateError("ZIP uncompressed size budget exceeded")
            if len(roots) != 1 or not next(iter(roots)).startswith("koschei-lang-"):
                raise PilotGateError("unexpected release root")
            missing = REQUIRED - relative
            if missing:
                raise PilotGateError("ZIP missing required product fixtures: " + ", ".join(sorted(missing)))
            return actual, next(iter(roots))
    except (zipfile.BadZipFile, EOFError) as error:
        raise PilotGateError("invalid ZIP archive") from error


def pilot_checks(archive_path: Path, expected_sha256: str) -> dict:
    """Run only built-in safe examples from a *trusted* digest-matched ZIP."""
    actual, root_name = verify_archive(archive_path, expected_sha256)
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="koschei-pilot-gate-") as scratch:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(scratch)
        home = Path(scratch) / root_name
        # Do not forward development credentials or network proxy env vars.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": scratch,
            "PYTHONPATH": str(home),
            "PYTHONNOUSERSITE": "1",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }

        def check(name: str, args: tuple[str, ...], exit_code: int,
                  required_text: str | None = None,
                  exact_output: str | None = None) -> None:
            try:
                run = subprocess.run(
                    (sys.executable, "-m", "koschei", *args),
                    cwd=home, env=env, capture_output=True,
                    timeout=90, check=False,
                )
                stdout = run.stdout.decode("utf-8", errors="replace")
                stderr = run.stderr.decode("utf-8", errors="replace")
                passed = (
                    run.returncode == exit_code
                    and (required_text is None or required_text in stdout + stderr)
                    and (exact_output is None or stdout == exact_output)
                )
                results.append({
                    "id": name, "passed": passed, "exit_code": run.returncode,
                    "stdout_sha256": _sha256(run.stdout),
                    "stderr_sha256": _sha256(run.stderr),
                })
            except (subprocess.TimeoutExpired, OSError) as error:
                results.append({
                    "id": name, "passed": False, "error": type(error).__name__
                })

        check("bundled-hello", ("run", "examples/hello.ks"), 0,
              exact_output="Koschei\n1\n")
        check("ungiven-disk-denied-at-compile-time",
              ("check", "examples/supply_chain/main.ks"), 1,
              required_text="KS2401")
        for program in ("secretscan", "integrity"):
            file = f"examples/apps/{program}/main.ks"
            check(f"{program}-network-capability-denied-by-policy",
                  ("caps", "--deny", "net", file), 0)
            check(f"{program}-disk-access-visible-in-capability-manifest",
                  ("caps", "--deny", "disk", file), 2)

    return {
        "schema": SCHEMA,
        "artifact_sha256": actual,
        "archive_root": root_name,
        "pilot_checks_passed": all(x["passed"] for x in results),
        "checks": results,
        "approved_for_production": False,
        "security_scope": "bundled interpreter + static capability demo only",
        "not_proved": [
            "arbitrary external downloaded code sandboxed",
            "macOS, Homebrew, Python or Go host process compromise prevented",
            "developer credential theft prevented",
            "AI agent or wallet authorization protected",
            "production release, independent audit or bank deployment approved",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True,
                        help="Exact ZIP candidate from a trusted build")
    parser.add_argument("--expected-sha256", required=True,
                        help="Expected hash from an independent trusted channel")
    parser.add_argument("--output", type=Path, required=True,
                        help="Evidence JSON output, not inside the release ZIP")
    args = parser.parse_args(argv)
    try:
        evidence = pilot_checks(args.bundle, args.expected_sha256)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(evidence, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Pilot security gate: {'PASS' if evidence['pilot_checks_passed'] else 'FAIL'}")
        print(f"Evidence: {args.output}")
        return 0 if evidence["pilot_checks_passed"] else 2
    except (OSError, PilotGateError) as error:
        print(f"Pilot security gate refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
