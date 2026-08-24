"""Trusted CLI for building and verifying native-intelligence training exports."""
from __future__ import annotations

import argparse
from pathlib import Path

from .model_curriculum import ModelCurriculumError
from .model_curriculum_cli import verify_trusted_checkout
from .native_intelligence_holdout_v1 import build_native_intelligence_holdout_v1
from .native_intelligence_training_balance_v1 import (
    BALANCED_FAMILY_COUNT,
    build_balanced_native_training_corpus_v1,
)
from .native_intelligence_training_corpus_v1 import (
    DEFAULT_VARIANTS_PER_FAMILY,
    NativeTrainingCorpusError,
)
from .native_intelligence_training_export_v1 import (
    NativeTrainingExportError,
    load_native_training_export_manifest_v1,
    verify_native_training_export_v1,
    write_native_training_export_v1,
)
from .native_model_curriculum_v2 import (
    NativeModelCurriculumError,
    load_native_model_curriculum_v2,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-native-training-corpus",
        description="Build or verify a balanced sealed N0..N6 Koschei native-intelligence training corpus",
    )
    actions = parser.add_subparsers(dest="action", required=True)

    build = actions.add_parser("build")
    build.add_argument("--repo-root", default=".")
    build.add_argument("--curriculum", required=True)
    build.add_argument("--output-dir", required=True)
    build.add_argument(
        "--variants-per-family",
        type=int,
        default=DEFAULT_VARIANTS_PER_FAMILY,
    )

    verify = actions.add_parser("verify")
    verify.add_argument("directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "build":
            curriculum = load_native_model_curriculum_v2(args.curriculum)
            verify_trusted_checkout(Path(args.repo_root), curriculum.source_commit)
            holdout = build_native_intelligence_holdout_v1(curriculum)
            corpus = build_balanced_native_training_corpus_v1(
                holdout,
                variants_per_family=args.variants_per_family,
            )
            if len(corpus.family_splits) != BALANCED_FAMILY_COUNT:
                raise NativeTrainingCorpusError("trusted CLI requires balanced oracle family set")
            manifest = write_native_training_export_v1(
                holdout,
                corpus,
                args.output_dir,
            )
            print(f"KOSCHEI NATIVE TRAINING CORPUS: {args.output_dir}")
            print(f"SOURCE COMMIT: {corpus.source_commit}")
            print(f"CONSTITUTIONAL HOLDOUT: {holdout.digest}")
            print(f"ORACLE FAMILIES: {len(corpus.family_splits)}")
            print(f"EXAMPLES: {corpus.example_count}")
            for split, count in corpus.split_counts:
                print(f"{split.upper()}: {count}")
            print(f"CORPUS SHA256: {corpus.digest}")
            print(f"EXPORT MANIFEST: {manifest.digest}")
        else:
            directory = Path(args.directory)
            manifest = load_native_training_export_manifest_v1(directory / "manifest.json")
            verify_native_training_export_v1(manifest, directory)
            print(f"KOSCHEI NATIVE TRAINING CORPUS VERIFIED: {directory}")
            print(f"SOURCE COMMIT: {manifest.source_commit}")
            print(f"EXAMPLES: {manifest.corpus_example_count}")
            print(f"CORPUS SHA256: {manifest.corpus_digest}")
            print(f"EXPORT MANIFEST: {manifest.digest}")
        return 0
    except (
        ModelCurriculumError,
        NativeModelCurriculumError,
        NativeTrainingCorpusError,
        NativeTrainingExportError,
        FileExistsError,
        OSError,
    ) as error:
        print(f"ks-native-training-corpus: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
