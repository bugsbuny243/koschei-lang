"""CLI for comparing two independently verified Koschei native builds."""

from __future__ import annotations

import argparse
import json
import sys

from .build_manifest import (
    BuildManifestError,
    load_native_manifest,
    verify_native_manifest,
)
from .lexer import LexerError
from .mir import MirIntegrityError
from .module_lock import ModuleLockError, load_module_lock
from .modules import ModuleError
from .parser import ParserError
from .reproducibility import (
    ReproducibilityError,
    compare_verified_builds,
    write_reproducibility_report,
)
from .semantic import SemanticError


def add_build_compare_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "build-compare",
        help="Compare two verified native builds for byte reproducibility",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )
    for side in ("left", "right"):
        parser.add_argument(f"--{side}-source", required=True)
        parser.add_argument(f"--{side}-artifact", required=True)
        parser.add_argument(f"--{side}-manifest", required=True)
        parser.add_argument(f"--{side}-lockfile", required=True)
    parser.add_argument("--output", help="Write a sealed reproducibility report")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON")


def command_build_compare(args: argparse.Namespace) -> int:
    try:
        left = verify_native_manifest(
            load_native_manifest(args.left_manifest),
            args.left_artifact,
            source=args.left_source,
            locked=load_module_lock(args.left_lockfile),
        )
        right = verify_native_manifest(
            load_native_manifest(args.right_manifest),
            args.right_artifact,
            source=args.right_source,
            locked=load_module_lock(args.right_lockfile),
        )
        report = compare_verified_builds(left, right)
        if args.output:
            write_reproducibility_report(report, args.output)
    except (
        OSError,
        ValueError,
        BuildManifestError,
        ReproducibilityError,
        ModuleLockError,
        ModuleError,
        MirIntegrityError,
        LexerError,
        ParserError,
        SemanticError,
    ) as error:
        code = getattr(error, "code", "KS1920")
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": code,
                        "message": str(error),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1

    result = report.to_dict()
    result["ok"] = report.byte_reproducible
    if args.output:
        result["output"] = args.output
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        locale = getattr(args, "lang", "en")
        if report.status == "byte_identical":
            label = "BAYT-AYNI" if locale == "tr" else "BYTE-IDENTICAL"
        elif report.status == "artifact_mismatch":
            label = "ARTIFACT FARKLI" if locale == "tr" else "ARTIFACT MISMATCH"
        else:
            label = "KARŞILAŞTIRILAMAZ" if locale == "tr" else "NOT COMPARABLE"
        print(f"KOSCHEI REPRODUCIBILITY: {label}")
        print(f"LEFT SHA256: {report.left_artifact_sha256}")
        print(f"RIGHT SHA256: {report.right_artifact_sha256}")
        print(f"REPORT DIGEST: {report.report_digest}")

    if report.status == "byte_identical":
        return 0
    if report.status == "not_comparable":
        return 2
    return 3
