"""Unified Koschei command entrypoint.

The compiler CLI historically lived in :mod:`koschei.cli`, while the language
server was installed only as the separate ``ks-lsp`` executable. This adapter
keeps the existing CLI implementation stable, exposes ``ks lsp``, attaches V5
interpreter runtime budgets to the public ``ks run`` path, enforces optional
locked native builds and manifests, and hosts the sealed foreign-contract,
maturity, differential-fuzzing, foundation-export, module-lock, native-build
verification, reproducibility, release proof, and maturity-attestation commands.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import cli as _cli
from .build_manifest import (
    BuildManifestError,
    build_native_manifest,
    write_native_manifest,
)
from .build_manifest_cli import add_build_verify_parser, command_build_verify
from .differential_fuzz_cli import add_differential_fuzz_parser, command_differential_fuzz
from .foreign_cli import add_foreign_parser, command_foreign
from .foundation_export_cli import add_foundation_export_parser, command_foundation_export
from .lock_cli import add_lock_parser, command_lock
from .maturity_attestation_cli import add_maturity_attest_parser, command_maturity_attest
from .maturity_cli import add_maturity_parser, command_maturity
from .mir import require_mir
from .mir_go_native import generate_go_mir_native, inspect_mir_go_support
from .module_lock import load_module_lock, verify_module_lock
from .modules import check_graph
from .release_proof_cli import add_release_proof_parser, command_release_proof
from .reproducibility_cli import (
    add_build_compare_parser,
    add_build_compare_verify_parser,
    command_build_compare,
    command_build_compare_verify,
)
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
    add_maturity_attest_parser(subcommands)
    add_differential_fuzz_parser(subcommands)
    add_foundation_export_parser(subcommands)
    add_lock_parser(subcommands)
    add_build_verify_parser(subcommands)
    add_build_compare_parser(subcommands)
    add_build_compare_verify_parser(subcommands)
    add_release_proof_parser(subcommands)

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
    build.add_argument(
        "--build-manifest",
        help=(
            "Write a SHA-256 build manifest binding the lock, MIR, toolchain, "
            "and native artifact; requires --locked"
        ),
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


def _compile_mir_go(go_source: str, target: Path, locale: str) -> int:
    go_binary = shutil.which("go")
    if go_binary is None:
        message = (
            "KOSCHEI ERROR: 'go' was not found. Install Go for native builds "
            "or use 'ks run'."
            if locale == "en"
            else "KOSCHEI ERROR: 'go' bulunamadı. Native derleme için Go kurun "
            "veya 'ks run' kullanın."
        )
        print(message, file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="koschei-mir-build-") as workspace:
        directory = Path(workspace)
        (directory / "main.go").write_text(go_source, encoding="utf-8")
        (directory / "go.mod").write_text(
            "module koscheiprogram\n\ngo 1.21\n", encoding="utf-8"
        )
        completed = subprocess.run(
            [go_binary, "build", "-o", str(target), "."],
            cwd=directory,
            capture_output=True,
            text=True,
        )
    if completed.returncode != 0:
        message = (
            "KOSCHEI ERROR: MIR-Go compilation failed. This is a compiler bug; "
            "report it with the source file.\n"
            if locale == "en"
            else "KOSCHEI ERROR: MIR-Go derlemesi başarısız oldu. Bu bir derleyici "
            "hatasıdır; kaynak dosyayla birlikte bildirin.\n"
        )
        print(message + completed.stderr.strip(), file=sys.stderr)
        return 1
    print(f"KOSCHEI BUILD: {target}")
    return 0


def native_build_mode(mir) -> str:
    """Return the deterministic backend selected for a checked native build."""

    return "mir_go_v1" if inspect_mir_go_support(mir).supported else "ast_go_compat_v1"


def _build_with_public_lock(args: argparse.Namespace) -> int:
    """Verify the lock before native build work and optionally attest the artifact."""

    original = _cli.command_build

    def command(path: str, output: str | None, locale: str) -> int:
        if args.lockfile and not args.locked:
            raise ValueError("--lockfile requires --locked")
        if args.build_manifest and not args.locked:
            raise ValueError("--build-manifest requires --locked")

        source = _cli.require_ks_extension(path)
        verified_lock = None
        if args.locked:
            lock_path = args.lockfile or str(source.parent / "koschei.lock.json")
            verified_lock = verify_module_lock(source, load_module_lock(lock_path))

        manifest_path = Path(args.build_manifest) if args.build_manifest else None
        if manifest_path is not None and manifest_path.exists():
            raise BuildManifestError(
                "KS1911",
                f"build manifest already exists: {manifest_path}",
            )

        graph = _cli.open_graph(path)
        check_graph(graph)
        mir = require_mir(graph)
        target = (Path(output) if output else source.with_suffix("")).resolve()
        if native_build_mode(mir) == "mir_go_v1":
            result = _compile_mir_go(generate_go_mir_native(mir), target, locale)
        else:
            result = original(path, output, locale)
        if result != 0 or manifest_path is None:
            return result
        if verified_lock is None:
            raise BuildManifestError("KS1910", "verified module lock is missing")

        go_binary = shutil.which("go")
        if go_binary is None:
            raise BuildManifestError("KS1910", "Go toolchain identity is unavailable")
        toolchain = subprocess.run(
            [go_binary, "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if toolchain.returncode != 0 or not toolchain.stdout.strip():
            raise BuildManifestError("KS1910", "could not read Go toolchain identity")

        manifest = build_native_manifest(
            target,
            module_lock_digest=verified_lock.lock_digest,
            mir_version=str(mir.version),
            mir_fingerprint=mir.fingerprint,
            backend_toolchain=toolchain.stdout,
        )
        write_native_manifest(manifest, manifest_path)
        print(f"KOSCHEI BUILD MANIFEST: {manifest_path}")
        print(f"ARTIFACT SHA256: {manifest.artifact_sha256}")
        return 0

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
    if args.command == "maturity-attest":
        return command_maturity_attest(args)
    if args.command == "differential-fuzz":
        return command_differential_fuzz(args)
    if args.command == "foundation-export":
        return command_foundation_export(args)
    if args.command == "lock":
        return command_lock(args)
    if args.command == "build-verify":
        return command_build_verify(args)
    if args.command == "build-compare":
        return command_build_compare(args)
    if args.command == "build-compare-verify":
        return command_build_compare_verify(args)
    if args.command == "release-proof":
        return command_release_proof(args)
    if args.command == "run":
        return _run_with_public_budget(args)
    if args.command == "build":
        return _build_with_public_lock(args)
    return _cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
