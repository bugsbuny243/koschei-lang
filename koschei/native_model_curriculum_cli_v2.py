"""Trusted release CLI for Koschei native-intelligence curriculum v2."""
from __future__ import annotations

import argparse
from pathlib import Path

from .model_curriculum import ModelCurriculumError
from .model_curriculum_cli import verify_trusted_checkout
from .native_model_curriculum_v2 import (
    NativeModelCurriculumError,
    build_native_model_curriculum_v2,
    load_native_model_curriculum_v2,
    write_native_model_curriculum_v2,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-native-model-curriculum",
        description="Build or verify the Khar/oracle-backed Koschei native-intelligence curriculum v2",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build")
    build.add_argument("--repo-root", default=".")
    build.add_argument("--source-commit", required=True)
    build.add_argument("--parent-curriculum-sha256", required=True)
    build.add_argument("--output", required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("curriculum")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "build":
            try:
                verify_trusted_checkout(Path(args.repo_root), args.source_commit)
            except ModelCurriculumError as error:
                raise NativeModelCurriculumError(str(error)) from error
            curriculum = build_native_model_curriculum_v2(
                source_commit=args.source_commit,
                parent_curriculum_digest=args.parent_curriculum_sha256,
            )
            write_native_model_curriculum_v2(curriculum, args.output)
            print(f"KOSCHEI NATIVE MODEL CURRICULUM: {args.output}")
        else:
            curriculum = load_native_model_curriculum_v2(args.curriculum)
            print(f"KOSCHEI NATIVE MODEL CURRICULUM VERIFIED: {args.curriculum}")

        print(f"SOURCE COMMIT: {curriculum.source_commit}")
        print(f"PARENT CURRICULUM: {curriculum.parent_curriculum_digest}")
        print(f"CASES: {curriculum.case_count}")
        print(f"ACCEPTED: {curriculum.accepted_count}")
        print(f"REJECTED: {curriculum.rejected_count}")
        print(f"N0: {curriculum.stage_counts['N0']}")
        print(f"N2: {curriculum.stage_counts['N2']}")
        print(f"CURRICULUM SHA256: {curriculum.curriculum_sha256}")
        return 0
    except (NativeModelCurriculumError, FileExistsError, OSError) as error:
        print(f"ks-native-model-curriculum: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
