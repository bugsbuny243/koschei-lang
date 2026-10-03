"""Run Koschei validation without GitHub-hosted Actions."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform as platform_module
import subprocess
import sys

from .local_validation_v1 import (
    LocalValidationError,
    seal_local_validation_receipt_v1,
    seal_local_validation_step_v1,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_external_path(path: Path, label: str) -> None:
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        return
    raise LocalValidationError(
        f"{label} must live outside the repository checkout; use /tmp or the Drive validation vault"
    )


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise LocalValidationError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.decode("utf-8", errors="strict").strip()


def _command_version(command: tuple[str, ...]) -> str:
    try:
        proc = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError:
        return "unavailable"
    output = proc.stdout.decode("utf-8", errors="replace").strip()
    return output.splitlines()[0] if output else f"exit-{proc.returncode}"


def _steps(profile: str, candidate: str, adversarial_json: Path, sbom_json: Path) -> tuple[tuple[str, tuple[str, ...]], ...]:
    steps: list[tuple[str, tuple[str, ...]]] = [
        (
            "python-import-preflight",
            (
                sys.executable,
                "-c",
                "import koschei, pytest; print('koschei+pytest import: PASS')",
            ),
        ),
        (
            "pytest-suite",
            (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests",
            ),
        ),
        (
            "lang-sentinel-separation",
            (
                sys.executable,
                "-m",
                "koschei.lang_project_boundary_v1",
                "--repo-root",
                ".",
            ),
        ),
        ("verify-script-syntax", ("bash", "-n", "verify.sh")),
        (
            "repository-truth",
            (sys.executable, "tools/run_repository_truth_v4.py"),
        ),
        (
            "adversarial-lab-v2",
            (
                sys.executable,
                "tools/run_adversarial_lab.py",
                "--candidate",
                candidate,
                "--json-out",
                str(adversarial_json),
            ),
        ),
    ]
    if profile == "full":
        steps.extend(
            [
                (
                    "reproducible-sbom",
                    (
                        sys.executable,
                        "tools/acquisition_sbom_v1.py",
                        "--output",
                        str(sbom_json),
                        "--require-reproducible",
                    ),
                ),
                ("ceremony", ("bash", "bench/ceremony/check.sh")),
                ("vscode-extension-syntax", ("node", "--check", "editors/vscode/extension.js")),
                (
                    "vscode-json-syntax",
                    (
                        sys.executable,
                        "-c",
                        "import json; from pathlib import Path; "
                        "[json.loads(Path(p).read_text(encoding='utf-8')) for p in "
                        "('editors/vscode/package.json','editors/vscode/language-configuration.json','editors/vscode/syntaxes/koschei.tmLanguage.json')]; "
                        "print('VS Code JSON: PASS')",
                    ),
                ),
            ]
        )
    return tuple(steps)


def _run_step(
    index: int,
    step_id: str,
    command: tuple[str, ...],
    evidence_dir: Path,
):
    try:
        proc = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=os.environ.copy(),
        )
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except OSError as error:
        returncode = 127
        stdout = b""
        stderr = f"{type(error).__name__}: {error}\n".encode("utf-8", errors="replace")

    prefix = f"{index:02d}-{step_id}"
    (evidence_dir / f"{prefix}.stdout.log").write_bytes(stdout)
    (evidence_dir / f"{prefix}.stderr.log").write_bytes(stderr)
    return seal_local_validation_step_v1(
        step_id=step_id,
        command=command,
        returncode=returncode,
        stdout_sha256=_sha256(stdout),
        stderr_sha256=_sha256(stderr),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-local-validate",
        description="Run Koschei release validation without GitHub-hosted Actions",
    )
    parser.add_argument("--profile", choices=("core", "full"), default="full")
    parser.add_argument("--output", required=True, help="receipt JSON path outside the checkout")
    parser.add_argument("--evidence-dir", required=True, help="stdout/stderr evidence directory outside the checkout")
    parser.add_argument(
        "--development",
        action="store_true",
        help="allow a dirty checkout; receipt can pass but is never release-eligible",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    if output.exists():
        print(f"ks-local-validate: output already exists: {output}", file=sys.stderr)
        return 64
    if evidence_dir.exists():
        print(f"ks-local-validate: evidence directory already exists: {evidence_dir}", file=sys.stderr)
        return 64

    try:
        _require_external_path(output, "validation receipt")
        _require_external_path(evidence_dir, "validation evidence directory")
        source_commit = _git("rev-parse", "HEAD").lower()
        checkout_clean = _git("status", "--porcelain", "--untracked-files=normal") == ""
        if not checkout_clean and not args.development:
            raise LocalValidationError(
                "working tree is dirty; commit/stash changes or use --development for non-release evidence"
            )

        evidence_dir.mkdir(parents=True, exist_ok=False)
        adversarial_json = evidence_dir / "adversarial-lab-report.json"
        sbom_json = evidence_dir / "acquisition-sbom.json"
        step_results = []
        for index, (step_id, command) in enumerate(
            _steps(args.profile, source_commit, adversarial_json, sbom_json),
            start=1,
        ):
            print(f"[{index}] {step_id}: {' '.join(command)}", flush=True)
            result = _run_step(index, step_id, command, evidence_dir)
            step_results.append(result)
            print("    PASS" if result.passed else f"    FAIL ({result.returncode})", flush=True)

        receipt = seal_local_validation_receipt_v1(
            source_commit=source_commit,
            checkout_clean=checkout_clean,
            profile=args.profile,
            python_version=sys.version.replace("\n", " "),
            go_version=_command_version(("go", "version")),
            platform=platform_module.platform(),
            steps=tuple(step_results),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(asdict(receipt), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"VALIDATION RECEIPT: {output}")
        print(f"VALIDATION SHA256: {receipt.digest}")
        print(f"PASSED: {receipt.passed}")
        print(f"RELEASE ELIGIBLE: {receipt.release_eligible}")
        if not receipt.passed:
            return 2
        if args.profile == "full" and not receipt.release_eligible:
            return 3
        return 0
    except (LocalValidationError, OSError) as error:
        print(f"ks-local-validate: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
