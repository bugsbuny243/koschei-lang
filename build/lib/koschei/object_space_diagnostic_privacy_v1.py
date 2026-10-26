"""Prevent canonical Object Space identities from escaping through diagnostics.

Compiler semantic identity remains the full object id. Human/source diagnostics
use a deliberately non-semantic locator so logs do not become a durable map from
errors to canonical object identities.
"""

from __future__ import annotations

from pathlib import Path

from . import object_space_graph_v1 as _graph
from .lexer import LexerError
from .parser import ParserError, parse

_INSTALLED = False
_ORIGINAL_LOAD_MODULE_GRAPH = None

_DIAGNOSTIC_PATH = Path("<object-space>")


def _private_decode_source(payload: object, object_id: bytes):
    del object_id
    if not isinstance(payload, bytes):
        _graph._fail("graph source payload must be bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise _graph.ObjectSpaceGraphError("graph source object is not UTF-8") from error
    try:
        program = parse(text)
    except (LexerError, ParserError) as error:
        error.source_path = _DIAGNOSTIC_PATH
        raise
    return text, program


def _private_load_module_graph(project):
    assert _ORIGINAL_LOAD_MODULE_GRAPH is not None
    graph = _ORIGINAL_LOAD_MODULE_GRAPH(project)
    for module in graph.modules.values():
        module.path = _DIAGNOSTIC_PATH
    return graph


def install_object_space_diagnostic_privacy_v1() -> None:
    global _INSTALLED, _ORIGINAL_LOAD_MODULE_GRAPH
    if _INSTALLED:
        return
    _graph._decode_source = _private_decode_source
    _ORIGINAL_LOAD_MODULE_GRAPH = _graph.load_object_space_module_graph
    _graph.load_object_space_module_graph = _private_load_module_graph
    _INSTALLED = True
