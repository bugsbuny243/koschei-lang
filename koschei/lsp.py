"""Koschei için küçük, sıfır-bağımlılıklı Language Server Protocol sunucusu.

İlk sürüm full-document sync, anlık lexer/parser/semantic tanıları ve document
formatting sağlar. Protokol taşıması yalnız stdio üzerindeki standart Content-Length
çerçevesidir; compiler paketine üçüncü taraf bağımlılık eklenmez.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from .ast_nodes import EnumDeclaration, FunctionDeclaration, StructDeclaration

from .formatter import format_source
from .integrity import check_program_integrity
from .lexer import LexerError
from .parser import ParserError, parse
from .semantic import SemanticError, check

_LOCATION = re.compile(r"\[satır (\d+), sütun (\d+)\]")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KEYWORDS = (
    "fn", "let", "mut", "return", "if", "else", "while", "for", "in",
    "struct", "enum", "match", "import", "or", "true", "false",
)
_BUILTIN_TYPES = (
    "String", "Int", "Float", "Bool", "Void", "Error", "List", "Map",
    "Option", "Result", "SystemCaps", "NetCaps", "DiskCaps", "DiskReadCaps",
    "EnvCaps", "ProcessCaps",
)
_KEYWORD_HELP = {
    "fn": "Fonksiyon bildirimi başlatır.",
    "let": "Değişmez yerel değer tanımlar.",
    "mut": "Değiştirilebilir yerel değer tanımlar.",
    "return": "Fonksiyondan çıkar ve isteğe bağlı bir değer döndürür.",
    "match": "Enum/Option/Result değerlerini exhaustive biçimde eşler.",
    "or": "Option/Result/Error akışında fallback veya erken dönüş sağlar.",
    "struct": "Adlandırılmış alanları olan yapısal veri tipi tanımlar.",
    "enum": "Varyantlardan oluşan cebirsel veri tipi tanımlar.",
    "import": "Aynı proje içindeki bir Koschei modülünü bağlar.",
}


def _location_of(error: Exception) -> tuple[int, int]:
    location = getattr(error, "location", None)
    if location is not None:
        return max(0, location.line - 1), max(0, location.column - 1)
    match = _LOCATION.search(str(error))
    if match is None:
        return 0, 0
    return max(0, int(match.group(1)) - 1), max(0, int(match.group(2)) - 1)


def diagnostics_for_source(source: str) -> list[dict[str, Any]]:
    """Tek bir açık doküman için LSP diagnostic listesi üretir."""

    try:
        program = parse(source)
        check_program_integrity(program)
        check(program)
    except (LexerError, ParserError, SemanticError) as error:
        line, character = _location_of(error)
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


def _range(line: int, column: int, length: int = 1) -> dict[str, Any]:
    start_line = max(0, line - 1)
    start_column = max(0, column - 1)
    return {
        "start": {"line": start_line, "character": start_column},
        "end": {"line": start_line, "character": start_column + max(1, length)},
    }


def _name_range(source: str, line: int, column: int, name: str) -> dict[str, Any]:
    lines = source.splitlines()
    line_index = max(0, line - 1)
    if line_index < len(lines):
        start = lines[line_index].find(name, max(0, column - 1))
        if start >= 0:
            return {
                "start": {"line": line_index, "character": start},
                "end": {"line": line_index, "character": start + len(name)},
            }
    return _range(line, column, len(name))


def _word_at(source: str, position: dict[str, Any]) -> str | None:
    lines = source.splitlines()
    line_index = position.get("line")
    character = position.get("character")
    if not isinstance(line_index, int) or not isinstance(character, int):
        return None
    if line_index < 0 or line_index >= len(lines):
        return None
    line = lines[line_index]
    for match in _WORD.finditer(line):
        if match.start() <= character <= match.end():
            return match.group(0)
    return None


def _symbol_entries(source: str) -> list[dict[str, Any]]:
    try:
        program = parse(source)
    except (LexerError, ParserError):
        return []

    entries: list[dict[str, Any]] = []
    for declaration in program.declarations:
        assert isinstance(declaration, FunctionDeclaration)
        params = ", ".join(
            f"{parameter.name}: {parameter.type_ref}" for parameter in declaration.parameters
        )
        result = str(declaration.return_type) if declaration.return_type else "Void"
        entries.append(
            {
                "name": declaration.name,
                "kind": 12,
                "detail": f"fn {declaration.name}({params}) -> {result}",
                "range": _name_range(
                    source,
                    declaration.location.line,
                    declaration.location.column,
                    declaration.name,
                ),
            }
        )
    for declaration in program.structs:
        assert isinstance(declaration, StructDeclaration)
        fields = ", ".join(f"{field.name}: {field.type_ref}" for field in declaration.fields)
        entries.append(
            {
                "name": declaration.name,
                "kind": 23,
                "detail": f"struct {declaration.name} {{ {fields} }}",
                "range": _name_range(
                    source,
                    declaration.location.line,
                    declaration.location.column,
                    declaration.name,
                ),
            }
        )
    for declaration in program.enums:
        assert isinstance(declaration, EnumDeclaration)
        variants = " | ".join(
            variant.name
            + (f"({variant.payload_type})" if variant.payload_type else "")
            for variant in declaration.variants
        )
        entries.append(
            {
                "name": declaration.name,
                "kind": 10,
                "detail": f"enum {declaration.name} = {variants}",
                "range": _name_range(
                    source,
                    declaration.location.line,
                    declaration.location.column,
                    declaration.name,
                ),
            }
        )
    return entries


def hover_for_source(source: str, position: dict[str, Any]) -> dict[str, Any] | None:
    word = _word_at(source, position)
    if word is None:
        return None
    for entry in _symbol_entries(source):
        if entry["name"] == word:
            return {
                "contents": {"kind": "markdown", "value": f"```koschei\n{entry['detail']}\n```"}
            }
    if word in _KEYWORD_HELP:
        return {"contents": {"kind": "markdown", "value": f"**{word}** — {_KEYWORD_HELP[word]}"}}
    if word in _BUILTIN_TYPES:
        return {"contents": {"kind": "markdown", "value": f"`{word}` Koschei yerleşik tipidir."}}
    return None


def definition_for_source(
    uri: str, source: str, position: dict[str, Any]
) -> dict[str, Any] | None:
    word = _word_at(source, position)
    if word is None:
        return None
    for entry in _symbol_entries(source):
        if entry["name"] == word:
            return {"uri": uri, "range": entry["range"]}
    return None


def document_symbols_for_source(source: str) -> list[dict[str, Any]]:
    return [
        {
            "name": entry["name"],
            "detail": entry["detail"],
            "kind": entry["kind"],
            "range": entry["range"],
            "selectionRange": entry["range"],
        }
        for entry in _symbol_entries(source)
    ]


def completion_items() -> list[dict[str, Any]]:
    keywords = [{"label": value, "kind": 14} for value in _KEYWORDS]
    types = [{"label": value, "kind": 7} for value in _BUILTIN_TYPES]
    return keywords + types


def formatting_edits(source: str) -> list[dict[str, Any]]:
    formatted = format_source(source)
    if formatted == source:
        return []
    line_count = source.count("\n") + 1
    return [
        {
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": line_count, "character": 0},
            },
            "newText": formatted,
        }
    ]


@dataclass(slots=True)
class LspServer:
    documents: dict[str, str] = field(default_factory=dict)
    shutdown_requested: bool = False
    exit_requested: bool = False

    def handle(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            return [
                self._response(
                    request_id,
                    {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "documentFormattingProvider": True,
                            "hoverProvider": True,
                            "definitionProvider": True,
                            "documentSymbolProvider": True,
                            "completionProvider": {"triggerCharacters": ["."]},
                        },
                        "serverInfo": {"name": "koschei-lsp", "version": "0.1"},
                    },
                )
            ]

        if method == "initialized":
            return []

        if method == "shutdown":
            self.shutdown_requested = True
            return [self._response(request_id, None)]

        if method == "exit":
            self.exit_requested = True
            return []

        if method == "textDocument/didOpen":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            text = document.get("text")
            if isinstance(uri, str) and isinstance(text, str):
                self.documents[uri] = text
                return [self._publish(uri, text)]
            return []

        if method == "textDocument/didChange":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            changes = params.get("contentChanges") or []
            if isinstance(uri, str) and changes:
                text = changes[-1].get("text")
                if isinstance(text, str):
                    self.documents[uri] = text
                    return [self._publish(uri, text)]
            return []

        if method == "textDocument/didClose":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            if isinstance(uri, str):
                self.documents.pop(uri, None)
                return [self._notification("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})]
            return []

        if method == "textDocument/formatting":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            source = self.documents.get(uri, "") if isinstance(uri, str) else ""
            return [self._response(request_id, formatting_edits(source))]

        if method == "textDocument/hover":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            position = params.get("position") or {}
            source = self.documents.get(uri, "") if isinstance(uri, str) else ""
            return [self._response(request_id, hover_for_source(source, position))]

        if method == "textDocument/definition":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            position = params.get("position") or {}
            source = self.documents.get(uri, "") if isinstance(uri, str) else ""
            result = (
                definition_for_source(uri, source, position)
                if isinstance(uri, str)
                else None
            )
            return [self._response(request_id, result)]

        if method == "textDocument/documentSymbol":
            document = params.get("textDocument") or {}
            uri = document.get("uri")
            source = self.documents.get(uri, "") if isinstance(uri, str) else ""
            return [self._response(request_id, document_symbols_for_source(source))]

        if method == "textDocument/completion":
            return [self._response(request_id, completion_items())]

        if request_id is not None:
            return [
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            ]
        return []

    @staticmethod
    def _response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "method": method, "params": params}

    def _publish(self, uri: str, source: str) -> dict[str, Any]:
        return self._notification(
            "textDocument/publishDiagnostics",
            {"uri": uri, "diagnostics": diagnostics_for_source(source)},
        )


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        name, separator, value = line.decode("ascii", errors="strict").partition(":")
        if not separator:
            continue
        headers[name.strip().lower()] = value.strip()

    length_text = headers.get("content-length")
    if length_text is None:
        return None
    length = int(length_text)
    payload = stream.read(length)
    if len(payload) != length:
        return None
    value = json.loads(payload.decode("utf-8"))
    return value if isinstance(value, dict) else None


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
    stream.write(payload)
    stream.flush()


def run_stdio(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    source = stdin or sys.stdin.buffer
    target = stdout or sys.stdout.buffer
    server = LspServer()

    while not server.exit_requested:
        message = read_message(source)
        if message is None:
            break
        for response in server.handle(message):
            write_message(target, response)

    return 0 if server.shutdown_requested or server.exit_requested else 1


def main() -> int:
    """Console entry point for the zero-dependency Koschei LSP server."""
    return run_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
