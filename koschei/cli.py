#!/usr/bin/env python3
"""Koschei compiler prototipi için ilk komut satırı aracı."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from .capabilities import DOMAIN_ORDER, analyze as analyze_capabilities, render as render_manifest, to_dict as manifest_to_dict
from .capabilities import analyze_graph
from .codegen_go import CodegenError, generate_go
from .modules import (
    ModuleError,
    check_graph,
    enum_declarations,
    load_graph,
    module_imports,
    namespaces,
)
from .diagnostics import known_codes, lookup as lookup_diagnostic
from .formatter import check_source, format_source
from .interpreter import KoscheiRuntimeError, run as interpret
from .lexer import LexerError, tokenize
from .parser import ParserError, parse
from .semantic import SemanticError, check as semantic_check


def require_ks_extension(path: str) -> Path:
    source_path = Path(path)
    if source_path.suffix != ".ks":
        raise ValueError("Koschei kaynak dosyası '.ks' uzantılı olmalıdır.")
    return source_path


def read_source(path: str) -> str:
    return require_ks_extension(path).read_text(encoding="utf-8")


def open_graph(path: str):
    """Kök dosyayı doğrular ve modül grafiğini yükler."""
    require_ks_extension(path)
    return load_graph(path)


def command_tokens(path: str) -> int:
    for token in tokenize(read_source(path)):
        print(token)
    return 0


def command_ast(path: str) -> int:
    program = parse(read_source(path))
    print(json.dumps(asdict(program), ensure_ascii=False, indent=2))
    return 0


def command_check(path: str) -> int:
    graph = open_graph(path)
    report = check_graph(graph)
    module_count = len(graph.modules)
    suffix = f", {module_count} modül" if module_count > 1 else ""
    print(
        f"KOSCHEI CHECK: PASS ({report.functions} fonksiyon, "
        f"{report.variables} değişken, {report.capability_values} capability değeri"
        f"{suffix})"
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


def command_fmt(path: str, write: bool, check_only: bool) -> int:
    source = read_source(path)
    formatted = format_source(source)

    if check_only:
        if formatted == source:
            return 0
        print(
            f"KOSCHEI FMT: {path} kanonik biçimde değil "
            "('koschei.py fmt --write' ile düzeltin).",
            file=sys.stderr,
        )
        return 1

    if write:
        if formatted == source:
            print(f"KOSCHEI FMT: {path} zaten kanonik biçimde.")
            return 0
        Path(path).write_text(formatted, encoding="utf-8")
        print(f"KOSCHEI FMT: {path} yeniden biçimlendirildi.")
        return 0

    print(formatted, end="")
    return 0


def command_caps(path: str, as_json: bool, denied: list[str] | None) -> int:
    graph = open_graph(path)
    check_graph(graph)
    # Manifesto tüm grafiği kapsar: içe aktarılan modüllerin talep ettiği
    # yetkiler de programın saldırı yüzeyine dahildir.
    manifest = analyze_graph(graph)

    if as_json:
        print(json.dumps(manifest_to_dict(manifest, path), ensure_ascii=False, indent=2))
    else:
        print(render_manifest(manifest, path), end="")

    if not denied:
        return 0

    violations = sorted(set(manifest.domains()) & set(denied))
    if violations:
        print(
            "KOSCHEI POLICY: reddedilen yetki alanı talep edildi: "
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


def command_build(path: str, output: str | None) -> int:
    graph = open_graph(path)
    check_graph(graph)
    go_source = generate_go(graph.root_module.program, graph)

    go_binary = shutil.which("go")
    if go_binary is None:
        print(
            "KOSCHEI ERROR: 'go' bulunamadı. Native derleme için Go kurulu olmalıdır "
            "(https://go.dev/dl). Go kurmadan çalıştırmak için 'koschei.py run' "
            "kullanabilir, üretilen Go kaynağını görmek için 'koschei.py emit-go' "
            "çalıştırabilirsiniz.",
            file=sys.stderr,
        )
        return 1

    source_path = Path(path)
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
        print(
            "KOSCHEI ERROR: Go derlemesi başarısız oldu. Bu bir derleyici hatasıdır; "
            "lütfen kaynak dosyayla birlikte bildirin.\n" + completed.stderr.strip(),
            file=sys.stderr,
        )
        return 1

    print(f"KOSCHEI BUILD: {target}")
    return 0


def command_explain(code: str) -> int:
    diagnostic = lookup_diagnostic(code)
    if diagnostic is None:
        print(
            f"KOSCHEI ERROR: '{code}' bilinen bir hata kodu değil. "
            f"Bilinen kodlar: {', '.join(known_codes())}",
            file=sys.stderr,
        )
        return 1
    print(diagnostic.render())
    return 0


def print_explain_hint(message: str) -> None:
    """Hata metninde bir KS kodu varsa 'explain' komutunu önerir."""
    diagnostic = lookup_diagnostic(message)
    if diagnostic is not None:
        print(
            f"İpucu: bu hatanın açıklaması için "
            f"'python koschei.py explain {diagnostic.code}' çalıştırın.",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog="koschei",
        description="Koschei (.ks) compiler prototipi",
    )
    subcommands = cli.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("tokens", "Lexer tokenlarını yazdırır"),
        ("ast", "Parser AST çıktısını JSON olarak yazdırır"),
        ("check", "Sözdizimi, değişmezlik ve capability kurallarını doğrular"),
        ("run", "Koschei programını yorumlayıcı ile çalıştırır"),
        ("emit-go", "Üretilen Go ara kaynağını yazdırır (Go kurulumu gerekmez)"),
    ):
        command = subcommands.add_parser(name, help=help_text)
        command.add_argument("source", help=".ks kaynak dosyası")

    formatter = subcommands.add_parser(
        "fmt",
        help="Kaynağı kanonik Koschei biçimine getirir",
    )
    formatter.add_argument("source", help=".ks kaynak dosyası")
    formatter.add_argument(
        "-w", "--write", action="store_true", help="Dosyayı yerinde günceller"
    )
    formatter.add_argument(
        "--check",
        action="store_true",
        help="Biçim bozuksa çıkış kodu 1 döner (CI kapısı); dosyayı değiştirmez",
    )

    caps = subcommands.add_parser(
        "caps",
        help="Programın erişebildiği yetkileri listeler (yetki manifestosu)",
    )
    caps.add_argument("source", help=".ks kaynak dosyası")
    caps.add_argument(
        "--json", action="store_true", help="Manifestoyu JSON olarak yazdırır"
    )
    caps.add_argument(
        "--deny",
        action="append",
        choices=list(DOMAIN_ORDER),
        help=(
            "Belirtilen yetki alanı talep edilirse çıkış kodu 2 döner "
            "(CI politikası için; birden fazla kez kullanılabilir)"
        ),
    )

    build = subcommands.add_parser(
        "build", help="Koschei programını tek bir native binary olarak derler"
    )
    build.add_argument("source", help=".ks kaynak dosyası")
    build.add_argument("-o", "--output", help="Çıktı binary yolu")

    explain = subcommands.add_parser(
        "explain", help="Bir Koschei hata kodunu açıklar ve düzeltme örneği verir"
    )
    explain.add_argument("code", help="Hata kodu (ör. KS2403) veya kodu içeren hata metni")

    return cli


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "tokens":
            return command_tokens(args.source)
        if args.command == "ast":
            return command_ast(args.source)
        if args.command == "check":
            return command_check(args.source)
        if args.command == "run":
            return command_run(args.source)
        if args.command == "fmt":
            return command_fmt(args.source, args.write, args.check)
        if args.command == "caps":
            return command_caps(args.source, args.json, args.deny)
        if args.command == "emit-go":
            return command_emit_go(args.source)
        if args.command == "build":
            return command_build(args.source, args.output)
        if args.command == "explain":
            return command_explain(args.code)
    except KoscheiRuntimeError as error:
        print(f"KOSCHEI RUNTIME ERROR: {error}", file=sys.stderr)
        print_explain_hint(str(error))
        return 1
    except (
        OSError,
        ValueError,
        LexerError,
        ParserError,
        SemanticError,
        CodegenError,
        ModuleError,
    ) as error:
        print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
        print_explain_hint(str(error))
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
