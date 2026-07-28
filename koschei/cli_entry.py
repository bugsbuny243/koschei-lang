"""Unified Koschei command entrypoint.

The compiler CLI historically lived in :mod:`koschei.cli`, while the language
server was installed only as the separate ``ks-lsp`` executable. This adapter
keeps the existing CLI implementation stable, exposes ``ks lsp``, and attaches
V5 interpreter runtime budgets to the public ``ks run`` path.
"""

from __future__ import annotations

import argparse
import sys

from . import cli as _cli
from .mir import require_mir
from .modules import check_graph
from .runtime_budget import (
    DEFAULT_MAX_STEPS,
    HARD_MAX_CALL_DEPTH,
    bounded_call_depth,
    positive_step_budget,
    run_mir_with_budget,
)


def _budget_argument(parser, value: str) -> int:
    try:
        return parser(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_parser() -> argparse.ArgumentParser:
    """Return the public CLI parser including LSP and runtime policy options."""

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

    run = subcommands.choices["run"]
    run.add_argument(
        "--max-steps",
        type=lambda value: _budget_argument(positive_step_budget, value),
        default=DEFAULT_MAX_STEPS,
        help=f"Interpreter step budget (default: {DEFAULT_MAX_STEPS})",
    )
    run.add_argument(
        "--max-call-depth",
        type=lambda value: _budget_argument(bounded_call_depth, value),
        default=HARD_MAX_CALL_DEPTH,
        help=f"Koschei call-frame budget (1..{HARD_MAX_CALL_DEPTH})",
    )
    return parser


def command_lsp() -> int:
    """Start the V5 typed-analysis LSP lazily so ordinary CLI startup stays small."""

    from .lsp_v5 import main as lsp_main

    return lsp_main()


def _run_with_public_budget(args: argparse.Namespace) -> int:
    """Reuse the compiler CLI's diagnostics while replacing only run execution."""

    original = _cli.command_run

    def command(path: str) -> int:
        graph = _cli.open_graph(path)
        check_graph(graph)
        return run_mir_with_budget(
            require_mir(graph),
            [],
            max_steps=args.max_steps,
            max_call_depth=args.max_call_depth,
        )

    _cli.command_run = command
    try:
        return _cli.main(["--lang", args.lang, "run", args.source])
    finally:
        _cli.command_run = original


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(arguments)
    if args.command == "lsp":
        return command_lsp()
    if args.command == "run":
        return _run_with_public_budget(args)
    return _cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
