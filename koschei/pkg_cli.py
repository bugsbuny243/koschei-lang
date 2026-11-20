"""``ks pkg``: pinned package dependencies (Packages v1, phase 1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .packages_v1 import (
    SURFACE_ORDER,
    PackageError,
    SurfaceWidened,
    load_lock,
    load_project_packages,
    sync,
    verify_project,
)


def add_pkg_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "pkg",
        help="Fetch, lock and verify package dependencies with their capability surfaces",
    )
    parser.add_argument("--lang", choices=("en", "tr"), default=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="pkg_command", required=True)

    sync_parser = commands.add_parser(
        "sync", help="Fetch dependencies, compute their surfaces and write the lock"
    )
    sync_parser.add_argument("project", nargs="?", default=".", help="Project directory")
    sync_parser.add_argument(
        "--allow",
        action="append",
        choices=SURFACE_ORDER,
        default=[],
        help="Accept an update that adds this capability (repeatable)",
    )
    sync_parser.add_argument("--json", action="store_true", help="Emit JSON")

    verify_parser = commands.add_parser(
        "verify", help="Check the lock and every vendored byte"
    )
    verify_parser.add_argument("project", nargs="?", default=".")
    verify_parser.add_argument("--json", action="store_true")

    list_parser = commands.add_parser("list", help="Show locked packages and their surfaces")
    list_parser.add_argument("project", nargs="?", default=".")
    list_parser.add_argument("--json", action="store_true")


def _surface_text(surface) -> str:
    return ", ".join(surface) if surface else "pure"


def command_pkg(args: argparse.Namespace) -> int:
    project = Path(args.project)
    try:
        if args.pkg_command == "sync":
            result = sync(project, allow=frozenset(args.allow))
            if args.json:
                print(json.dumps({
                    "ok": True,
                    "packages": [
                        {
                            "name": change.name,
                            "change": change.kind,
                            "version": change.version,
                            "surface": list(change.surface),
                            "added": list(change.added_capabilities),
                        }
                        for change in result.changes
                    ],
                }, indent=2, sort_keys=True))
            else:
                for change in result.changes:
                    line = f"{change.kind:<9} {change.name} {change.version}: {_surface_text(change.surface)}"
                    if change.kind == "updated" and change.added_capabilities:
                        line += f"  (allowed: {', '.join(change.added_capabilities)})"
                    print(line)
                if not result.changes:
                    print("no dependencies")
            return 0
        if args.pkg_command == "verify":
            resolver = verify_project(project)
            count = len(resolver.lock.packages)
            if args.json:
                print(json.dumps({"ok": True, "packages": count}))
            else:
                print(f"KOSCHEI PKG VERIFY: PASS ({count} packages)")
            return 0
        if args.pkg_command == "list":
            load_project_packages(project)
            lock = load_lock(project.resolve())
            packages = lock.packages if lock else {}
            if args.json:
                print(json.dumps(packages, indent=2, sort_keys=True))
            else:
                for name, entry in sorted(packages.items()):
                    print(f"{name} {entry['version']}: {_surface_text(entry['surface'])}")
                if not packages:
                    print("no locked packages")
            return 0
    except SurfaceWidened as error:
        print(f"KOSCHEI PKG: {error}", file=sys.stderr)
        return 3
    except PackageError as error:
        print(f"KOSCHEI PKG ERROR: KS1606: {error}", file=sys.stderr)
        return 1
    raise AssertionError(args.pkg_command)
