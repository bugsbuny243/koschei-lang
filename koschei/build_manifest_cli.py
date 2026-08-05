"""CLI for verifying Koschei native build manifests against source and bytes."""

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
from .semantic import SemanticError


def add_build_verify_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "build-verify",
        help="Verify a native artifact against its lock, MIR, and build manifest",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )
    parser.add_argument("source", help="Root .ks source file")
    parser.add_argument("--artifact", required=True, help="Native artifact path")
    parser.add_argument("--manifest", required=True, help="Build manifest path")
    parser.add_argument("--lockfile", required=True, help="Module lockfile path")
    parser.add_argument("--json", action="store_true", help="Emit stable JSON")


def command_build_verify(args: argparse.Namespace) -> int:
    try:
        verified = verify_native_manifest(
            load_native_manifest(args.manifest),
            args.artifact,
            source=args.source,
            locked=load_module_lock(args.lockfile),
        )
    except (
        OSError,
        ValueError,
        BuildManifestError,
        ModuleLockError,
        ModuleError,
        MirIntegrityError,
        LexerError,
        ParserError,
        SemanticError,
    ) as error:
        code = getattr(error, "code", "KS1912")
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": code,
                        "message": str(error),
                        "artifact": args.artifact,
                        "manifest": args.manifest,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1

    result = {
        "ok": True,
        "artifact": args.artifact,
        "artifact_sha256": verified.artifact_sha256,
        "module_lock_digest": verified.module_lock_digest,
        "mir_version": verified.mir_version,
        "mir_fingerprint": verified.mir_fingerprint,
        "compiler_version": verified.compiler_version,
        "backend": verified.backend,
        "backend_toolchain": verified.backend_toolchain,
        "manifest_digest": verified.manifest_digest,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    locale = getattr(args, "lang", "en")
    if locale == "tr":
        print("KOSCHEI BUILD VERIFY: GEÇTİ")
    else:
        print("KOSCHEI BUILD VERIFY: PASS")
    print(f"ARTIFACT SHA256: {verified.artifact_sha256}")
    print(f"MANIFEST DIGEST: {verified.manifest_digest}")
    return 0
