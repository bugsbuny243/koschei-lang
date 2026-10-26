"""Fail-closed integrity guard for the generated Serve Go helper block.

The Serve backend is assembled through installer overlays. This guard keeps known
helper-template transcription/escape defects from reaching generated Go and
asserts the repaired forms are present. It patches both the source helper template
and the already-installed capability runtime so repeated generation is stable.
"""

from __future__ import annotations

from . import codegen_go as _codegen
from . import serve_loopback_exchange_go_v1 as _serve_go

_INSTALLED = False

_BROKEN = '''\t\tif n == 0 { return ksServeIO("response write sıfır byte ilerleme yaptı")\n\t}\n\treturn nil'''
_FIXED = '''\t\tif n == 0 { return ksServeIO("response write sıfır byte ilerleme yaptı") }\n\t}\n\treturn nil'''

_RAW_TAB_RUNE = "if byteValue == '\t' { continue }"
_ESCAPED_TAB_RUNE = r"if byteValue == '\t' { continue }"
_RAW_TAB_TRIM = 'strings.Trim(line[separator+1:], " \t")'
_ESCAPED_TAB_TRIM = r'strings.Trim(line[separator+1:], " \t")'


def _repair(source: str, *, label: str) -> str:
    if _BROKEN in source:
        source = source.replace(_BROKEN, _FIXED, 1)
    if _FIXED not in source:
        raise RuntimeError(
            f"Serve Go write-all integrity marker missing in {label}; fail-closed."
        )
    return source


def _repair_installed_tab_escapes(source: str) -> str:
    # serve_loopback_exchange_go_v1 historically normalized literal ``\\t``
    # sequences while inserting the helper block. That transformation is useful
    # for no semantic content here and can also touch Go escape sequences inside
    # quoted literals. Restore the explicit escapes in the installed runtime.
    source = source.replace(_RAW_TAB_RUNE, _ESCAPED_TAB_RUNE)
    source = source.replace(_RAW_TAB_TRIM, _ESCAPED_TAB_TRIM)
    if _ESCAPED_TAB_RUNE not in source or _ESCAPED_TAB_TRIM not in source:
        raise RuntimeError(
            "Serve Go tab-escape integrity markers are missing; fail-closed."
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
    _codegen.CAPABILITY_RUNTIME = _repair_installed_tab_escapes(
        _repair(
            _codegen.CAPABILITY_RUNTIME,
            label="installed capability runtime",
        )
    )
    _INSTALLED = True
