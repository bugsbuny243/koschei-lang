"""Trusted CLI boundary for compiler-oracle model curriculum releases."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .model_curriculum import (
    ModelCurriculumError,
    build_model_curriculum,
    load_model_curriculum,
    write_model_curriculum,
)


def verify_trusted_checkout(repo_root: str | Path, source_commit: str) -> None:
    """Require the attributed commit to be HEAD and the complete worktree clean.

    Foundation export intentionally checks only foundation-source paths. A model
    curriculum also depends on compiler and generator implementation bytes, so
    its trusted CLI release path is stricter and rejects any tracked or untracked
    worktree mutation outside ignored build artifacts.
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ModelCurriculumError(f"repository root does not exist: {root}")

    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if head.strip() != source_commit:
        raise ModelCurriculumError(
            "source_commit does not match the checked-out Git HEAD commit"
        )

    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status.strip():
        raise ModelCurriculumError(
            "trusted model curriculum export requires a completely clean Git worktree"
        )


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ModelCurriculumError(
            "git is required for trusted model curriculum export"
        ) from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or "unknown git error"
        raise ModelCurriculumError(
            f"git {' '.join(arguments[:2])} failed: {message}"
        )
    return completed.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-model-curriculum",
        description="Build or verify the compiler-oracle Koschei model curriculum",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build")
    build.add_argument("--repo-root", default=".")
    build.add_argument("--source-commit", required=True)
    build.add_argument("--output", required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("curriculum")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "build":
            verify_trusted_checkout(args.repo_root, args.source_commit)
            curriculum = build_model_curriculum(
                args.repo_root,
                source_commit=args.source_commit,
            )
            write_model_curriculum(curriculum, args.output)
            print(f"KOSCHEI MODEL CURRICULUM: {args.output}")
        else:
            curriculum = load_model_curriculum(args.curriculum)
            print(f"KOSCHEI MODEL CURRICULUM VERIFIED: {args.curriculum}")
        print(f"SOURCE COMMIT: {curriculum.source_commit}")
        print(f"COMPILER VERSION: {curriculum.compiler_version}")
        print(f"CASES: {curriculum.case_count}")
        print(f"ACCEPTED: {curriculum.accepted_count}")
        print(f"REJECTED: {curriculum.rejected_count}")
        print(f"CURRICULUM SHA256: {curriculum.curriculum_sha256}")
        return 0
    except (ModelCurriculumError, FileExistsError, OSError) as exc:
        print(f"ks-model-curriculum: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
