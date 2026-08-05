"""Unified Koschei command entrypoint.

The compiler CLI historically lived in :mod:`koschei.cli`, while the language
server was installed only as the separate ``ks-lsp`` executable. This adapter
keeps the existing CLI implementation stable, exposes ``ks lsp``, attaches V5
interpreter runtime budgets to the public ``ks run`` path, enforces optional
locked native builds, and hosts the sealed foreign-contract, maturity, and
module-lock validation commands.
"""

from __future__ import annotations

import argparse
import sys

from . import cli as _cli
from .foreign_cli import add_foreign_parser, command_foreign
from .lock_cli import add_lock_parser, command_lock
from .maturity_cli import add_maturity_parser, command_maturity
from .mir import require_mir
from .module_lock import load_module_lock, verify_module_lock
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

    add_foreign_parser(subcommands)
    add_maturity_parser(subcommands)
    add_lock_parser(subcommands)

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

    build = subcommands.choices["build"]
    build.add_argument(
        "--locked",
        action="store_true",
        help="Verify the complete module graph against a lockfile before compiling",
    )
    build.add_argument(
        "--lockfile",
        help="Lockfile path; defaults to koschei.lock.json beside the entry source",
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


def _build_with_public_lock(args: argparse.Namespace) -> int:
    """Verify the lock before any native build work while reusing CLI diagnostics."""

    original = _cli.command_build

    def command(path: str, output: str | None, locale: str) -> int:
        if args.lockfile and not args.locked:
            raise ValueError("--lockfile requires --locked")
        source = _cli.require_ks_extension(path)
        if args.locked:
            lock_path = args.lockfile or str(source.parent / "koschei.lock.json")
            verify_module_lock(source, load_module_lock(lock_path))
        return original(path, output, locale)

    forwarded = ["--lang", args.lang, "build", args.source]
    if args.output:
        forwarded.extend(["--output", args.output])

    _cli.command_build = command
    try:
        return _cli.main(forwarded)
    finally:
        _cli.command_build = original


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(arguments)
    if args.command == "lsp":
        return command_lsp()
    if args.command == "foreign":
        return command_foreign(args)
    if args.command == "maturity":
        return command_maturity(args)
    if args.command == "lock":
        return command_lock(args)
    if args.command == "run":
        return _run_with_public_budget(args)
    if args.command == "build":
        return _build_with_public_lock(args)
    return _cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
