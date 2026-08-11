"""Public CLI for fail-closed Koschei workspaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capabilities import DOMAIN_ORDER, analyze_graph
from .lexer import LexerError
from .mir import MirIntegrityError
from .modules import ModuleError, check_graph
from .parser import ParserError
from .semantic import SemanticError
from .workspace import (
    WorkspaceError,
    build_workspace_lock,
    load_workspace,
    load_workspace_lock,
    verify_workspace_lock,
    write_workspace_lock,
)
from .workspace_modules import load_workspace_member_graph


def add_workspace_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "workspace",
        help="Validate and lock a multi-project Koschei monorepo",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )
    commands = parser.add_subparsers(dest="workspace_command", required=True)

    check = commands.add_parser(
        "check",
        help="Check every workspace member in deterministic dependency order",
    )
    check.add_argument("path", nargs="?", default=".", help="Workspace root or manifest")
    check.add_argument("--json", action="store_true", help="Emit stable JSON")

    caps = commands.add_parser(
        "caps",
        help="Aggregate capability domains across all workspace members",
    )
    caps.add_argument("path", nargs="?", default=".", help="Workspace root or manifest")
    caps.add_argument("--json", action="store_true", help="Emit stable JSON")
    caps.add_argument(
        "--deny",
        action="append",
        choices=list(DOMAIN_ORDER),
        help="Exit 2 when any workspace member requests this capability domain",
    )

    lock = commands.add_parser("lock", help="Create or verify a workspace lock")
    lock_commands = lock.add_subparsers(dest="workspace_lock_command", required=True)
    create = lock_commands.add_parser("create", help="Create a deterministic workspace lock")
    create.add_argument("path", nargs="?", default=".", help="Workspace root or manifest")
    create.add_argument("--output", help="Output path; defaults in the workspace root")
    create.add_argument("--force", action="store_true", help="Explicitly replace an existing lock")
    create.add_argument("--json", action="store_true", help="Emit stable JSON")

    verify = lock_commands.add_parser("verify", help="Verify the complete workspace against a lock")
    verify.add_argument("path", nargs="?", default=".", help="Workspace root or manifest")
    verify.add_argument("--lock", help="Lock path; defaults in the workspace root")
    verify.add_argument("--json", action="store_true", help="Emit stable JSON")


def command_workspace(args: argparse.Namespace) -> int:
    try:
        workspace = load_workspace(args.path)
        if args.workspace_command == "check":
            result = _check_workspace(workspace)
            return _emit_check(result, args)
        if args.workspace_command == "caps":
            result = _workspace_caps(workspace)
            return _emit_caps(result, args)
        if args.workspace_command == "lock":
            return _command_workspace_lock(workspace, args)
        raise WorkspaceError("unsupported workspace command")
    except (
        OSError,
        WorkspaceError,
        LexerError,
        ParserError,
        SemanticError,
        ModuleError,
        MirIntegrityError,
        ValueError,
    ) as error:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"ok": False, "message": str(error)},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        return 1


def _check_workspace(workspace) -> dict[str, object]:
    by_name = workspace.by_name
    members: list[dict[str, object]] = []
    functions = 0
    variables = 0
    capability_values = 0
    modules = 0
    for name in workspace.build_order:
        member = by_name[name]
        graph = load_workspace_member_graph(workspace, name)
        report = check_graph(graph)
        count = len(graph.modules)
        functions += report.functions
        variables += report.variables
        capability_values += report.capability_values
        modules += count
        members.append(
            {
                "name": name,
                "path": member.path,
                "dependencies": list(member.dependencies),
                "modules": count,
                "functions": report.functions,
                "variables": report.variables,
                "capability_values": report.capability_values,
            }
        )
    return {
        "ok": True,
        "workspace": str(workspace.manifest),
        "member_count": len(members),
        "build_order": list(workspace.build_order),
        "modules": modules,
        "functions": functions,
        "variables": variables,
        "capability_values": capability_values,
        "members": members,
    }


def _workspace_caps(workspace) -> dict[str, object]:
    by_name = workspace.by_name
    requested: set[str] = set()
    members: list[dict[str, object]] = []
    exact = True
    for name in workspace.build_order:
        member = by_name[name]
        graph = load_workspace_member_graph(workspace, name)
        check_graph(graph)
        manifest = analyze_graph(graph)
        domains = manifest.domains()
        requested.update(domains)
        exact = exact and manifest.is_exact
        members.append(
            {
                "name": name,
                "path": member.path,
                "domains": domains,
                "exact": manifest.is_exact,
            }
        )
    domains = [domain for domain in DOMAIN_ORDER if domain in requested]
    return {
        "ok": True,
        "workspace": str(workspace.manifest),
        "member_count": len(members),
        "domains": domains,
        "exact": exact,
        "members": members,
    }


def _emit_check(result: dict[str, object], args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    locale = getattr(args, "lang", "en")
    if locale == "tr":
        print(
            "KOSCHEI WORKSPACE CHECK: PASS "
            f"({result['member_count']} paket, {result['modules']} modül)"
        )
    else:
        print(
            "KOSCHEI WORKSPACE CHECK: PASS "
            f"({result['member_count']} packages, {result['modules']} modules)"
        )
    print("BUILD ORDER: " + " -> ".join(result["build_order"]))
    return 0


def _emit_caps(result: dict[str, object], args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        domains = result["domains"]
        rendered = ", ".join(domains) if domains else "none"
        print(f"KOSCHEI WORKSPACE CAPS: {rendered}")
        for member in result["members"]:
            member_domains = ", ".join(member["domains"]) if member["domains"] else "none"
            print(f"- {member['name']}: {member_domains}")

    denied = set(args.deny or ())
    violations = [domain for domain in result["domains"] if domain in denied]
    if violations:
        if not args.json:
            print(
                "KOSCHEI WORKSPACE POLICY: denied capability domain requested: "
                + ", ".join(violations),
                file=sys.stderr,
            )
        return 2
    return 0


def _command_workspace_lock(workspace, args: argparse.Namespace) -> int:
    default_lock = workspace.root / "koschei.workspace.lock.json"
    if args.workspace_lock_command == "create":
        destination = Path(args.output) if args.output else default_lock
        lock = build_workspace_lock(workspace)
        write_workspace_lock(lock, destination, replace=args.force)
        action = "created"
        lock_path = destination
    else:
        lock_path = Path(args.lock) if args.lock else default_lock
        lock = verify_workspace_lock(workspace, load_workspace_lock(lock_path))
        action = "verified"

    result = {
        "ok": True,
        "action": action,
        "workspace": str(workspace.manifest),
        "lockfile": str(lock_path),
        "members": len(lock.members),
        "build_order": list(lock.build_order),
        "workspace_digest": lock.workspace_digest,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    label = action.upper()
    print(f"KOSCHEI WORKSPACE LOCK: {label} ({len(lock.members)} packages)")
    print(f"WORKSPACE DIGEST: {lock.workspace_digest}")
    return 0
