"""CLI for comparing and verifying Koschei native-build reproducibility."""

from __future__ import annotations

import argparse
import json
import sys

from .build_manifest import (
    BuildManifestError,
    NativeBuildManifest,
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
    load_reproducibility_report,
    verify_reproducibility_report,
    write_reproducibility_report,
)
from .semantic import SemanticError

_ERRORS = (
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
)


def add_build_compare_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "build-compare",
        help="Compare two verified native builds for byte reproducibility",
    )
    _add_language(parser)
    _add_build_sides(parser)
    parser.add_argument("--output", help="Write a sealed reproducibility report")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON")


def add_build_compare_verify_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "build-compare-verify",
        help="Verify a sealed reproducibility report against both native builds",
    )
    _add_language(parser)
    _add_build_sides(parser)
    parser.add_argument("--report", required=True, help="Reproducibility report path")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON")


def command_build_compare(args: argparse.Namespace) -> int:
    try:
        left = _verify_side(args, "left")
        right = _verify_side(args, "right")
        report = compare_verified_builds(left, right)
        if args.output:
            write_reproducibility_report(report, args.output)
    except _ERRORS as error:
        return _render_error(args, error)

    result = report.to_dict()
    result["ok"] = report.byte_reproducible
    if args.output:
        result["output"] = args.output
    _render_report(args, result)

    if report.status == "byte_identical":
        return 0
    if report.status == "not_comparable":
        return 2
    return 3


def command_build_compare_verify(args: argparse.Namespace) -> int:
    try:
        left = _verify_side(args, "left")
        right = _verify_side(args, "right")
        report = verify_reproducibility_report(
            load_reproducibility_report(args.report),
            left,
            right,
        )
    except _ERRORS as error:
        return _render_error(args, error)

    result = report.to_dict()
    result.update({"ok": True, "verified": True, "report": args.report})
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        locale = getattr(args, "lang", "en")
        label = "DOĞRULANDI" if locale == "tr" else "VERIFIED"
        print(f"KOSCHEI REPRODUCIBILITY REPORT: {label}")
        print(f"STATUS: {report.status}")
        print(f"REPORT DIGEST: {report.report_digest}")
    return 0


def _verify_side(args: argparse.Namespace, side: str) -> NativeBuildManifest:
    return verify_native_manifest(
        load_native_manifest(getattr(args, f"{side}_manifest")),
        getattr(args, f"{side}_artifact"),
        source=getattr(args, f"{side}_source"),
        locked=load_module_lock(getattr(args, f"{side}_lockfile")),
    )


def _add_language(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )


def _add_build_sides(parser: argparse.ArgumentParser) -> None:
    for side in ("left", "right"):
        parser.add_argument(f"--{side}-source", required=True)
        parser.add_argument(f"--{side}-artifact", required=True)
        parser.add_argument(f"--{side}-manifest", required=True)
        parser.add_argument(f"--{side}-lockfile", required=True)


def _render_error(args: argparse.Namespace, error: Exception) -> int:
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


def _render_report(args: argparse.Namespace, result: dict[str, object]) -> None:
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    locale = getattr(args, "lang", "en")
    status = result["status"]
    if status == "byte_identical":
        label = "BAYT-AYNI" if locale == "tr" else "BYTE-IDENTICAL"
    elif status == "artifact_mismatch":
        label = "ARTIFACT FARKLI" if locale == "tr" else "ARTIFACT MISMATCH"
    else:
        label = "KARŞILAŞTIRILAMAZ" if locale == "tr" else "NOT COMPARABLE"
    print(f"KOSCHEI REPRODUCIBILITY: {label}")
    print(f"LEFT SHA256: {result['left_artifact_sha256']}")
    print(f"RIGHT SHA256: {result['right_artifact_sha256']}")
    print(f"REPORT DIGEST: {result['report_digest']}")
