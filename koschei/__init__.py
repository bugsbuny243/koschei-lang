"""Koschei (.ks) — capability-secure programlama dili.

Derleyici hattı bu paketin içinde yaşar:
    lexer -> parser -> ast_nodes -> semantic -> (modules) -> interpreter
                                             -> codegen_go (native)
Yardımcı araçlar: diagnostics (ks explain), formatter (ks fmt),
capabilities (ks caps).
"""

from .cli import main

__all__ = ["main"]
__version__ = "0.8.0a3"
