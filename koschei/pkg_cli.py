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
    sync_parser.add_argument(
        "--allow-new-signer",
        action="append",
        default=[],
        metavar="PACKAGE",
        help="Accept a registry package signed by a different key than before (repeatable)",
    )
    sync_parser.add_argument("--json", action="store_true", help="Emit JSON")

    verify_parser = commands.add_parser(
        "verify", help="Check the lock and every vendored byte"
    )
    verify_parser.add_argument("project", nargs="?", default=".")
    verify_parser.add_argument("--json", action="store_true")

    add_parser = commands.add_parser("add", help="Add a registry dependency (name@version) and sync")
    add_parser.add_argument("spec", help="name@version, for example hexfmt@1.2.0")
    add_parser.add_argument("project", nargs="?", default=".")

    publish_parser = commands.add_parser(
        "publish", help="Check a package and add it to a registry checkout"
    )
    publish_parser.add_argument("package", nargs="?", default=".", help="Package directory")
    publish_parser.add_argument("--registry", required=True, help="Registry checkout directory")
    publish_parser.add_argument("--key", required=True, help="Key file from 'ks pkg keygen'")
    publish_parser.add_argument("--allow-similar-name", action="store_true")

    keygen_parser = commands.add_parser("keygen", help="Create a publisher signing key")
    keygen_parser.add_argument("path", help="Where to write the secret key file (mode 0600)")

    sign_parser = commands.add_parser("sign", help="Sign a version published before signatures")
    sign_parser.add_argument("spec", help="name@version")
    sign_parser.add_argument("--registry", required=True)
    sign_parser.add_argument("--key", required=True)

    yank_parser = commands.add_parser("yank", help="Hide a published version from new installs")
    yank_parser.add_argument("spec", help="name@version")
    yank_parser.add_argument("--registry", required=True)
    yank_parser.add_argument("--undo", action="store_true")

    list_parser = commands.add_parser("list", help="Show locked packages and their surfaces")
    list_parser.add_argument("project", nargs="?", default=".")
    list_parser.add_argument("--json", action="store_true")


def _surface_text(surface) -> str:
    return ", ".join(surface) if surface else "pure"


def _split_spec(text: str) -> tuple[str, str]:
    from .packages_v1 import PACKAGE_NAME, VERSION

    name, _, version = text.partition("@")
    if not PACKAGE_NAME.fullmatch(name) or not VERSION.fullmatch(version):
        raise PackageError(f"expected name@MAJOR.MINOR.PATCH, got {text!r}")
    return name, version


def _add_dependency(manifest: str, name: str, version: str) -> str:
    import re
    import tomllib

    existing = tomllib.loads(manifest).get("dependencies", {})
    if name in existing:
        raise PackageError(f"{name!r} is already a dependency; edit koschei.toml to change it")
    line = f'{name} = {{ version = "{version}" }}\n'
    header = re.search(r"^\[dependencies\][ \t]*\r?\n", manifest, flags=re.M)
    if header:
        return manifest[: header.end()] + line + manifest[header.end():]
    return manifest.rstrip("\n") + "\n\n[dependencies]\n" + line


def command_pkg(args: argparse.Namespace) -> int:
    project = Path(getattr(args, "project", "."))
    try:
        if args.pkg_command == "sync":
            result = sync(
                project, allow=frozenset(args.allow), allow_new_signer=frozenset(args.allow_new_signer)
            )
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
        if args.pkg_command == "add":
            name, version = _split_spec(args.spec)
            manifest = project / "koschei.toml"
            original = manifest.read_text(encoding="utf-8")
            manifest.write_text(_add_dependency(original, name, version), encoding="utf-8")
            try:
                result = sync(project)
            except BaseException:
                manifest.write_text(original, encoding="utf-8")
                raise
            for change in result.changes:
                if change.kind != "unchanged":
                    print(f"{change.kind:<9} {change.name} {change.version}: {_surface_text(change.surface)}")
            return 0
        if args.pkg_command == "publish":
            from .registry_v1 import publish

            published = publish(
                args.package, args.registry, key=args.key, allow_similar_name=args.allow_similar_name
            )
            print(f"published {published.name} {published.version}: {_surface_text(published.surface)}")
            for path in published.files:
                print(f"  wrote {path}")
            return 0
        if args.pkg_command == "keygen":
            from .registry_v1 import keygen

            public = keygen(args.path)
            print(f"wrote secret key to {args.path} (keep it private)")
            print(f"public key: {public}")
            return 0
        if args.pkg_command == "sign":
            from .registry_v1 import sign_existing

            name, version = _split_spec(args.spec)
            signer = sign_existing(args.registry, name, version, key=args.key)
            print(f"signed {name} {version} with {signer}")
            return 0
        if args.pkg_command == "yank":
            from .registry_v1 import yank

            name, version = _split_spec(args.spec)
            yank(args.registry, name, version, undo=args.undo)
            print(f"{'unyanked' if args.undo else 'yanked'} {name} {version}")
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
