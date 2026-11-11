"""Installed entrypoint for Koschei workspace commands."""

from __future__ import annotations

import argparse
import sys

from .workspace_cli import add_workspace_parser, command_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ks-workspace",
        description="Validate and lock a multi-project Koschei monorepo",
    )
    subcommands = parser.add_subparsers(dest="root_command", required=True)
    add_workspace_parser(subcommands)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(["workspace", *arguments])
    return command_workspace(args)


if __name__ == "__main__":
    raise SystemExit(main())
