"""Typed-analysis bridge for the zero-dependency Koschei language server.

The transport/editor feature implementation stays in :mod:`koschei.lsp`. This
module replaces only its document diagnostic callback so the installed
``ks-lsp`` command uses the same V5 Typed HIR + compatibility pipeline as
``ks check``. The bridge remains intentionally small until the legacy semantic
pass is retired.
"""

from __future__ import annotations

from typing import Any

from . import lsp as _transport
from .integrity import check_program_integrity
from .legacy_generics import prepare_legacy_analysis
from .lexer import LexerError
from .parser import ParserError, parse
from .semantic import SemanticError, check
from .typed_hir import check_typed_hir


def diagnostics_for_source(source: str) -> list[dict[str, Any]]:
    """Return live diagnostics using the complete compiler analysis pipeline."""

    try:
        program = parse(source)
        check_program_integrity(program)
        typed_report = check_typed_hir(program)
        legacy_program, _ = prepare_legacy_analysis(program, {}, typed_report)
        check(legacy_program)
    except (LexerError, ParserError, SemanticError) as error:
        line, character = _transport._location_of(error)
        return [
            {
                "range": {
                    "start": {"line": line, "character": character},
                    "end": {"line": line, "character": character + 1},
                },
                "severity": 1,
                "code": getattr(error, "code", None),
                "source": "koschei",
                "message": getattr(error, "message", str(error)),
            }
        ]
    return []


_transport.diagnostics_for_source = diagnostics_for_source

LspServer = _transport.LspServer
read_message = _transport.read_message
write_message = _transport.write_message
run_stdio = _transport.run_stdio


def main() -> int:
    return run_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
