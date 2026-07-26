"""Unified Koschei command entrypoint.

The compiler CLI historically lived in :mod:`koschei.cli`, while the language
server was installed only as the separate ``ks-lsp`` executable.  This adapter
keeps the existing CLI implementation stable and exposes the same typed LSP as
``ks lsp``.  ``ks-lsp`` remains a compatibility alias.
"""

from __future__ import annotations

import argparse
import sys

from . import cli as _cli


def build_parser() -> argparse.ArgumentParser:
    """Return the public CLI parser including the LSP subcommand."""

    parser = _cli.build_parser()
    subcommands = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    lsp = subcommands.add_parser(
        "lsp",
        help="Start the Koschei Language Server over stdio",
        description=(
            "Start the zero-dependency Koschei Language Server Protocol process "
            "over standard input/output. Editors normally launch this command."
        ),
    )
    lsp.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )
    return parser


def command_lsp() -> int:
    """Start the V5 typed-analysis LSP lazily so ordinary CLI startup stays small."""

    from .lsp_v5 import main as lsp_main

    return lsp_main()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(arguments)
    if args.command == "lsp":
        return command_lsp()
    return _cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
