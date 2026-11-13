"""Lambdas: anonymous functions lifted to top-level functions by the parser.

``fn(x: Int) -> Bool { return x > 0 }`` in an expression is parsed into a
top-level function with a reserved ``__lambda_<line>_<column>`` name and the
expression becomes a reference to it (``koschei/parser.py``). Every later
stage therefore treats a lambda exactly like a named function.

A lambda does not capture: its body sees its parameters, other functions and
imported modules, never a variable of the enclosing function. Using one is
``KS1103`` with a hint to pass the value as a parameter, instead of a bare
undefined-name error.
"""

from __future__ import annotations

from . import semantic as _semantic
from .parser import LAMBDA_PREFIX

_INSTALLED = False
_ORIGINAL_CHECK_FUNCTION = None

CAPTURE_MESSAGE = (
    "Lambda çevresindeki fonksiyonun değişkenlerini kullanamaz ({detail}); değeri "
    "parametre olarak verin ya da adlandırılmış bir fonksiyon yazın."
)


def is_lambda_name(name: str) -> bool:
    return name.startswith(LAMBDA_PREFIX)


def _check_function(self, function) -> None:
    try:
        return _ORIGINAL_CHECK_FUNCTION(self, function)
    except _semantic.SemanticError as error:
        if error.code == "KS1101" and is_lambda_name(function.name):
            raise _semantic.SemanticError(
                "KS1103", CAPTURE_MESSAGE.format(detail=error.message), error.location
            ) from error
        raise


def install_lambda_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_FUNCTION
    if _INSTALLED:
        return
    _ORIGINAL_CHECK_FUNCTION = _semantic.SemanticChecker._check_function
    _semantic.SemanticChecker._check_function = _check_function
    _INSTALLED = True


__all__ = ["CAPTURE_MESSAGE", "install_lambda_v1", "is_lambda_name"]
