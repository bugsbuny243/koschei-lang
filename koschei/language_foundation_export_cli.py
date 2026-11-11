from __future__ import annotations

import argparse
import json
from pathlib import Path

from .language_foundation_export import (
    LanguageFoundationExportError,
    build_language_foundation_corpus,
    write_language_foundation_corpus,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-foundation-export",
        description="Export a provenance-pinned Koschei language corpus for offline model training",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Koschei repository containing the pinned Git commit",
    )
    parser.add_argument(
        "--source-commit",
        required=True,
        help="Exact lowercase 40-character Koschei Git commit SHA",
    )
    parser.add_argument("--output", required=True, help="New corpus JSON path")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        corpus = build_language_foundation_corpus(
            Path(args.repo_root),
            source_commit=args.source_commit,
        )
        path = write_language_foundation_corpus(corpus, args.output)
    except (LanguageFoundationExportError, FileExistsError, OSError, ValueError) as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"KOSCHEI FOUNDATION EXPORT: BLOCKED — {error}")
        return 3

    result = {
        "ok": True,
        "path": str(path),
        "source_commit": corpus["source_commit"],
        "document_count": corpus["document_count"],
        "family_count": corpus["family_count"],
        "total_bytes": corpus["total_bytes"],
        "corpus_sha256": corpus["corpus_sha256"],
        "production_integration_allowed": False,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("KOSCHEI FOUNDATION EXPORT: PASS")
        print(f"COMMIT: {corpus['source_commit']}")
        print(f"DOCUMENTS: {corpus['document_count']}")
        print(f"FAMILIES: {corpus['family_count']}")
        print(f"CORPUS SHA256: {corpus['corpus_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
