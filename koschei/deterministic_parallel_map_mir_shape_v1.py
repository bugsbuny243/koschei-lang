"""Align ``parallel_map`` with normalized direct-MIR List representation.

Normalized MIR represents List values as tuples so immutable sequence identity is
explicit inside the AST-free executor. The original direct-MIR parallel adapter
expected and returned Python lists, which made a language-level ``parallel_map``
call incompatible with MIR List literals and MIR iterators.
"""

from __future__ import annotations

from . import deterministic_parallel_map_v1 as _parallel
from . import interpreter as _ast_runtime
from . import mir_native_runtime as _mir

_INSTALLED = False
_ORIGINAL_INVOKE = None


def _invoke(self, callee, arguments):
    if not (
        isinstance(callee, _mir._BuiltinRef)
        and callee.name == _parallel._BUILTIN
    ):
        return _ORIGINAL_INVOKE(self, callee, arguments)

    if len(arguments) != 3:
        raise _mir.MirNativeRuntimeError("parallel_map expects 3 arguments")

    values, worker, max_workers = arguments
    if not isinstance(values, tuple):
        return _mir._ErrorValue("KS3921: parallel_map expects normalized List<scalar>")
    if not isinstance(worker, _mir._FunctionRef):
        return _mir._ErrorValue("KS3921: parallel_map expects a direct unary worker")
    if (
        type(max_workers) is not int
        or not _parallel._MIN_WORKERS <= max_workers <= _parallel._MAX_WORKERS
    ):
        return _mir._ErrorValue(
            "KS3920: parallel_map max_workers must be between 1 and 64"
        )
    if any(
        not _parallel._runtime_scalar(item)
        or _ast_runtime._contains_capability(item)
        for item in values
    ):
        return _mir._ErrorValue(
            "KS3921: parallel_map input items must be share-safe scalars"
        )

    results: list[object] = []
    for item in values:
        mapped = _ORIGINAL_INVOKE(self, worker, [item])
        if isinstance(mapped, _mir._ErrorValue):
            return mapped
        if (
            not _parallel._runtime_scalar(mapped)
            or _ast_runtime._contains_capability(mapped)
        ):
            return _mir._ErrorValue(
                "KS3923: parallel worker returned a non-scalar value"
            )
        results.append(mapped)

    return tuple(results)


def install_deterministic_parallel_map_mir_shape_v1() -> None:
    global _INSTALLED, _ORIGINAL_INVOKE
    if _INSTALLED:
        return
    _ORIGINAL_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _invoke
    _INSTALLED = True
