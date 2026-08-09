"""CLI for deterministic Koschei language foundation corpus export."""

from __future__ import annotations

import argparse

from .foundation_export import (
    FoundationExportError,
    build_foundation_corpus,
    load_foundation_corpus,
    write_foundation_corpus,
)


def add_foundation_export_parser(subcommands) -> None:
    parser = subcommands.add_parser(
        "foundation-export",
        help="Build or verify the authoritative Koschei language foundation corpus",
    )
    actions = parser.add_subparsers(dest="foundation_action", required=True)

    build = actions.add_parser("build", help="Build a pinned corpus from this repository")
    build.add_argument("--repo-root", default=".")
    build.add_argument("--source-commit", required=True)
    build.add_argument("--output", required=True)

    verify = actions.add_parser("verify", help="Verify an exported foundation corpus")
    verify.add_argument("corpus")


def command_foundation_export(args: argparse.Namespace) -> int:
    try:
        if args.foundation_action == "build":
            corpus = build_foundation_corpus(
                args.repo_root,
                source_commit=args.source_commit,
            )
            write_foundation_corpus(corpus, args.output)
            print(f"KOSCHEI FOUNDATION CORPUS: {args.output}")
        else:
            corpus = load_foundation_corpus(args.corpus)
            print(f"KOSCHEI FOUNDATION CORPUS VERIFIED: {args.corpus}")
        print(f"SOURCE COMMIT: {corpus.source_commit}")
        print(f"DOCUMENTS: {corpus.document_count}")
        print(f"FAMILIES: {corpus.family_count}")
        print(f"CORPUS SHA256: {corpus.corpus_sha256}")
        return 0
    except (FoundationExportError, FileExistsError, OSError) as exc:
        print(f"ks foundation-export: {exc}")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Koschei language foundation corpus")
    subcommands = parser.add_subparsers(dest="foundation_action", required=True)
    build = subcommands.add_parser("build")
    build.add_argument("--repo-root", default=".")
    build.add_argument("--source-commit", required=True)
    build.add_argument("--output", required=True)
    verify = subcommands.add_parser("verify")
    verify.add_argument("corpus")
    args = parser.parse_args(argv)
    return command_foundation_export(args)


if __name__ == "__main__":
    raise SystemExit(main())
