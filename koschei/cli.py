#!/usr/bin/env python3
"""Koschei command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .capabilities import DOMAIN_ORDER, analyze_graph
from .capabilities import render as render_manifest
from .capabilities import to_dict as manifest_to_dict
from .codegen_go import CodegenError, generate_go
from .diagnostics import (
    diagnostic_payload,
    known_codes,
    lookup as lookup_diagnostic,
    normalize_locale,
    render_error,
)
from .formatter import format_source
from .interpreter import KoscheiRuntimeError, run as interpret
from .lexer import LexerError, tokenize
from .modules import (
    ModuleError,
    check_graph,
    enum_declarations,
    load_graph,
    module_imports,
    namespaces,
)
from .parser import ParserError, parse
from .project import ProjectError, create_project, resolve_source
from .semantic import SemanticError


def require_ks_extension(path: str) -> Path:
    source_path = resolve_source(path)
    if source_path.suffix != ".ks":
        raise ValueError("Koschei source files must use the '.ks' extension.")
    return source_path


def read_source(path: str) -> str:
    return require_ks_extension(path).read_text(encoding="utf-8")


def open_graph(path: str):
    """Resolve a file or project path and load its module graph."""
    source = require_ks_extension(path)
    return load_graph(source)


def command_tokens(path: str) -> int:
    for token in tokenize(read_source(path)):
        print(token)
    return 0


def command_ast(path: str) -> int:
    program = parse(read_source(path))
    print(json.dumps(asdict(program), ensure_ascii=False, indent=2))
    return 0


def command_check(path: str, as_json: bool, locale: str) -> int:
    source = require_ks_extension(path)
    graph = load_graph(source)
    report = check_graph(graph)
    module_count = len(graph.modules)
    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "source": str(source),
                    "functions": report.functions,
                    "variables": report.variables,
                    "capability_values": report.capability_values,
                    "modules": module_count,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if locale == "en":
        suffix = f", {module_count} modules" if module_count > 1 else ""
        print(
            f"KOSCHEI CHECK: PASS ({report.functions} functions, "
            f"{report.variables} variables, "
            f"{report.capability_values} capability values{suffix})"
        )
    else:
        suffix = f", {module_count} modül" if module_count > 1 else ""
        print(
            f"KOSCHEI CHECK: PASS ({report.functions} fonksiyon, "
            f"{report.variables} değişken, "
            f"{report.capability_values} capability değeri{suffix})"
        )
    return 0


def command_run(path: str) -> int:
    graph = open_graph(path)
    check_graph(graph)
    root = graph.root_module
    return interpret(
        root.program,
        [],
        namespaces=namespaces(graph),
        imports=root.imports,
        enums=enum_declarations(graph),
        module_imports=module_imports(graph),
    )


def command_fmt(path: str, write: bool, check_only: bool, locale: str) -> int:
    source_path = require_ks_extension(path)
    source = source_path.read_text(encoding="utf-8")
    formatted = format_source(source)

    if check_only:
        if formatted == source:
            return 0
        if locale == "en":
            message = (
                f"KOSCHEI FMT: {source_path} is not canonical "
                "(run 'ks fmt --write' to fix it)."
            )
        else:
            message = (
                f"KOSCHEI FMT: {source_path} kanonik biçimde değil "
                "('ks fmt --write' ile düzeltin)."
            )
        print(message, file=sys.stderr)
        return 1

    if write:
        if formatted == source:
            message = (
                f"KOSCHEI FMT: {source_path} is already canonical."
                if locale == "en"
                else f"KOSCHEI FMT: {source_path} zaten kanonik biçimde."
            )
            print(message)
            return 0
        source_path.write_text(formatted, encoding="utf-8")
        message = (
            f"KOSCHEI FMT: reformatted {source_path}."
            if locale == "en"
            else f"KOSCHEI FMT: {source_path} yeniden biçimlendirildi."
        )
        print(message)
        return 0

    print(formatted, end="")
    return 0


def command_caps(path: str, as_json: bool, denied: list[str] | None) -> int:
    source = require_ks_extension(path)
    graph = load_graph(source)
    check_graph(graph)
    manifest = analyze_graph(graph)

    if as_json:
        print(
            json.dumps(
                manifest_to_dict(manifest, str(source)),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_manifest(manifest, str(source)), end="")

    if not denied:
        return 0

    violations = sorted(set(manifest.domains()) & set(denied))
    if violations:
        print(
            "KOSCHEI POLICY: denied capability domain requested: "
            + ", ".join(violations),
            file=sys.stderr,
        )
        return 2
    return 0


def command_emit_go(path: str) -> int:
    graph = open_graph(path)
    check_graph(graph)
    print(generate_go(graph.root_module.program, graph), end="")
    return 0


def command_build(path: str, output: str | None, locale: str) -> int:
    source_path = require_ks_extension(path)
    graph = load_graph(source_path)
    check_graph(graph)
    go_source = generate_go(graph.root_module.program, graph)

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

    target = Path(output) if output else source_path.with_suffix("")
    target = target.resolve()

    with tempfile.TemporaryDirectory(prefix="koschei-build-") as workspace:
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
            "KOSCHEI ERROR: Go compilation failed. This is a compiler bug; "
            "report it with the source file.\n"
            if locale == "en"
            else "KOSCHEI ERROR: Go derlemesi başarısız oldu. Bu bir derleyici "
            "hatasıdır; kaynak dosyayla birlikte bildirin.\n"
        )
        print(message + completed.stderr.strip(), file=sys.stderr)
        return 1

    print(f"KOSCHEI BUILD: {target}")
    return 0


def command_explain(code: str, locale: str) -> int:
    diagnostic = lookup_diagnostic(code, locale)
    if diagnostic is None:
        if locale == "en":
            message = (
                f"KOSCHEI ERROR: '{code}' is not a known error code. "
                f"Known codes: {', '.join(known_codes())}"
            )
        else:
            message = (
                f"KOSCHEI ERROR: '{code}' bilinen bir hata kodu değil. "
                f"Bilinen kodlar: {', '.join(known_codes())}"
            )
        print(message, file=sys.stderr)
        return 1
    print(diagnostic.render(locale))
    return 0


def command_new(name: str, destination: str | None, locale: str) -> int:
    project = create_project(name, destination)
    if locale == "en":
        print(f"KOSCHEI NEW: created {project.name} at {project.root}")
        print(f"Entry: {project.entry.relative_to(project.root)}")
    else:
        print(f"KOSCHEI NEW: {project.name} projesi oluşturuldu: {project.root}")
        print(f"Giriş: {project.entry.relative_to(project.root)}")
    return 0


def command_version(as_json: bool) -> int:
    if as_json:
        print(json.dumps({"name": "koschei-lang", "version": __version__}))
    else:
        print(f"Koschei {__version__}")
    return 0


def print_explain_hint(message: str, locale: str) -> None:
    diagnostic = lookup_diagnostic(message, locale)
    if diagnostic is None:
        return
    if locale == "en":
        hint = f"Hint: run 'ks --lang en explain {diagnostic.code}' for details."
    else:
        hint = f"İpucu: ayrıntı için 'ks --lang tr explain {diagnostic.code}' çalıştırın."
    print(hint, file=sys.stderr)


def _add_language_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )


def _source_command(
    subcommands: argparse._SubParsersAction,
    name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    command = subcommands.add_parser(name, help=help_text)
    _add_language_option(command)
    command.add_argument(
        "source",
        nargs="?",
        default=".",
        help=".ks source file, project directory, or koschei.toml",
    )
    return command


def build_parser() -> argparse.ArgumentParser:
    default_language = normalize_locale(os.environ.get("KOSCHEI_LANG", "en"))
    cli = argparse.ArgumentParser(
        prog="koschei",
        description="Koschei capability-secure compiler",
    )
    cli.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=default_language,
        help="Diagnostic language (default: KOSCHEI_LANG or en)",
    )
    subcommands = cli.add_subparsers(dest="command", required=True)

    _source_command(subcommands, "tokens", "Print lexer tokens")
    _source_command(subcommands, "ast", "Print the parser AST as JSON")
    check = _source_command(
        subcommands,
        "check",
        "Validate syntax, types, modules, and capability rules",
    )
    check.add_argument(
        "--json",
        action="store_true",
        help="Emit one stable JSON result for editor and CI integrations",
    )
    _source_command(subcommands, "run", "Run a Koschei program")
    _source_command(subcommands, "emit-go", "Print generated Go source")

    formatter = _source_command(
        subcommands,
        "fmt",
        "Format source into canonical Koschei style",
    )
    formatter.add_argument(
        "-w", "--write", action="store_true", help="Update the file in place"
    )
    formatter.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 when formatting differs; do not modify the file",
    )

    caps = _source_command(
        subcommands,
        "caps",
        "Render the program capability manifest",
    )
    caps.add_argument("--json", action="store_true", help="Emit JSON")
    caps.add_argument(
        "--deny",
        action="append",
        choices=list(DOMAIN_ORDER),
        help="Exit with code 2 when the program requests this capability domain",
    )

    build = _source_command(
        subcommands,
        "build",
        "Compile a Koschei program into one native binary",
    )
    build.add_argument("-o", "--output", help="Native binary output path")

    explain = subcommands.add_parser(
        "explain", help="Explain a Koschei error code and show a fix"
    )
    _add_language_option(explain)
    explain.add_argument("code", help="Error code or error text containing a code")

    new = subcommands.add_parser("new", help="Create a new Koschei project")
    _add_language_option(new)
    new.add_argument("name", help="Lowercase package name")
    new.add_argument(
        "--path",
        help="Destination directory (defaults to a directory named after the package)",
    )

    version = subcommands.add_parser("version", help="Print the Koschei version")
    _add_language_option(version)
    version.add_argument("--json", action="store_true", help="Emit JSON")

    return cli


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    locale = normalize_locale(args.lang)

    try:
        if args.command == "tokens":
            return command_tokens(args.source)
        if args.command == "ast":
            return command_ast(args.source)
        if args.command == "check":
            return command_check(args.source, args.json, locale)
        if args.command == "run":
            return command_run(args.source)
        if args.command == "fmt":
            return command_fmt(args.source, args.write, args.check, locale)
        if args.command == "caps":
            return command_caps(args.source, args.json, args.deny)
        if args.command == "emit-go":
            return command_emit_go(args.source)
        if args.command == "build":
            return command_build(args.source, args.output, locale)
        if args.command == "explain":
            return command_explain(args.code, locale)
        if args.command == "new":
            return command_new(args.name, args.path, locale)
        if args.command == "version":
            return command_version(args.json)
    except KoscheiRuntimeError as error:
        if args.command == "check" and getattr(args, "json", False):
            print(
                json.dumps(
                    diagnostic_payload(
                        str(error),
                        locale=locale,
                        source=getattr(args, "source", None),
                        error=error,
                    ),
                    ensure_ascii=False,
                )
            )
        else:
            print(
                f"KOSCHEI RUNTIME ERROR: "
                f"{render_error(str(error), locale=locale, error=error)}",
                file=sys.stderr,
            )
            print_explain_hint(str(error), locale)
        return 1
    except (
        OSError,
        ValueError,
        ProjectError,
        LexerError,
        ParserError,
        SemanticError,
        CodegenError,
        ModuleError,
    ) as error:
        if args.command == "check" and getattr(args, "json", False):
            print(
                json.dumps(
                    diagnostic_payload(
                        str(error),
                        locale=locale,
                        source=getattr(args, "source", None),
                        error=error,
                    ),
                    ensure_ascii=False,
                )
            )
        else:
            print(
                f"KOSCHEI ERROR: "
                f"{render_error(str(error), locale=locale, error=error)}",
                file=sys.stderr,
            )
            print_explain_hint(str(error), locale)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
