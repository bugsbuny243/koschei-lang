"""Fail-closed integrity guard for the generated Serve Go helper block.

The Serve backend is assembled through installer overlays. This guard keeps one
known helper-line transcription defect from reaching generated Go and also
asserts the repaired form is present. It patches both the source helper template
and the already-installed capability runtime so repeated generation is stable.
"""

from __future__ import annotations

from . import codegen_go as _codegen
from . import serve_loopback_exchange_go_v1 as _serve_go

_INSTALLED = False

_BROKEN = '''\t\tif n == 0 { return ksServeIO("response write sıfır byte ilerleme yaptı")\n\t}\n\treturn nil'''
_FIXED = '''\t\tif n == 0 { return ksServeIO("response write sıfır byte ilerleme yaptı") }\n\t}\n\treturn nil'''


def _repair(source: str, *, label: str) -> str:
    if _BROKEN in source:
        source = source.replace(_BROKEN, _FIXED, 1)
    if _FIXED not in source:
        raise RuntimeError(
            f"Serve Go write-all integrity marker missing in {label}; fail-closed."
        )
    return source


def install_serve_loopback_exchange_go_integrity_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    _serve_go._GO_SERVE_HELPERS = _repair(
        _serve_go._GO_SERVE_HELPERS,
        label="helper template",
    )
    _codegen.CAPABILITY_RUNTIME = _repair(
        _codegen.CAPABILITY_RUNTIME,
        label="installed capability runtime",
    )
    _INSTALLED = True
