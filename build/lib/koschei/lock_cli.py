"""CLI for deterministic Koschei module lockfiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .module_lock import (
    ModuleLockError,
    build_module_lock,
    load_module_lock,
    verify_module_lock,
    write_module_lock,
)


def add_lock_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "lock",
        help="Create or verify a SHA-256 lockfile for a Koschei module graph",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )
    commands = parser.add_subparsers(dest="lock_command", required=True)

    create = commands.add_parser("create", help="Create a deterministic module lockfile")
    create.add_argument("source", help="Root *.ks source file")
    create.add_argument("--output", help="Lockfile path; defaults beside the source")
    create.add_argument(
        "--force",
        action="store_true",
        help="Explicitly replace an existing lockfile",
    )
    create.add_argument("--json", action="store_true", help="Emit stable JSON")

    verify = commands.add_parser("verify", help="Verify source files against a lockfile")
    verify.add_argument("source", help="Root *.ks source file")
    verify.add_argument("--lock", help="Lockfile path; defaults beside the source")
    verify.add_argument("--json", action="store_true", help="Emit stable JSON")


def command_lock(args: argparse.Namespace) -> int:
    source = Path(args.source)
    default_lock = source.resolve().parent / "koschei.lock.json"
    try:
        if args.lock_command == "create":
            destination = Path(args.output) if args.output else default_lock
            lock = build_module_lock(source)
            write_module_lock(lock, destination, replace=args.force)
            result = {
                "ok": True,
                "action": "created",
                "source": str(source),
                "lockfile": str(destination),
                "modules": len(lock.modules),
                "lock_digest": lock.lock_digest,
            }
        else:
            lock_path = Path(args.lock) if args.lock else default_lock
            locked = load_module_lock(lock_path)
            verified = verify_module_lock(source, locked)
            result = {
                "ok": True,
                "action": "verified",
                "source": str(source),
                "lockfile": str(lock_path),
                "modules": len(verified.modules),
                "lock_digest": verified.lock_digest,
            }
    except (OSError, ModuleLockError, ValueError) as error:
        if getattr(args, "json", False):
            code = error.code if isinstance(error, ModuleLockError) else "KS1900"
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": code,
                        "message": str(error),
                        "source": str(source),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    locale = getattr(args, "lang", "en")
    action = result["action"]
    if locale == "tr":
        label = "OLUŞTURULDU" if action == "created" else "DOĞRULANDI"
        print(f"KOSCHEI LOCK: {label} ({result['modules']} modül)")
    else:
        label = "CREATED" if action == "created" else "VERIFIED"
        print(f"KOSCHEI LOCK: {label} ({result['modules']} modules)")
    print(f"LOCK DIGEST: {result['lock_digest']}")
    return 0
