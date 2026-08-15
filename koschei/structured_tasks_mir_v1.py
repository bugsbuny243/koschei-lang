"""Direct-MIR adapter for deterministic cooperative task scopes."""

from __future__ import annotations

from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from .structured_tasks import (
    TASK_RUNNING,
    StructuredTaskError,
    TaskScopeValue,
)

_BUILTINS = frozenset(
    {
        "task_scope",
        "task_spawn",
        "task_join_all",
        "task_pending",
        "task_capacity",
        "task_closed",
    }
)
_INSTALLED = False
_ORIGINAL_INVOKE = None
_ORIGINAL_TO_STRING = None


def _invoke(self, callee, arguments):
    if not (isinstance(callee, _mir._BuiltinRef) and callee.name in _BUILTINS):
        return _ORIGINAL_INVOKE(self, callee, arguments)

    expected = {
        "task_scope": 1,
        "task_spawn": 3,
        "task_join_all": 1,
        "task_pending": 1,
        "task_capacity": 1,
        "task_closed": 1,
    }[callee.name]
    if len(arguments) != expected:
        raise _mir.MirNativeRuntimeError(
            f"{callee.name} expects {expected} arguments"
        )

    if callee.name == "task_scope":
        try:
            return TaskScopeValue(arguments[0])
        except StructuredTaskError as error:
            return _mir._ErrorValue(str(error))

    scope = arguments[0]
    if not isinstance(scope, TaskScopeValue):
        return _mir._ErrorValue(f"KS3915: {callee.name} expects TaskScope")

    if callee.name == "task_spawn":
        worker, argument = arguments[1], arguments[2]
        if not isinstance(worker, _mir._FunctionRef):
            return _mir._ErrorValue(
                "KS3914: task worker must be a unary named function"
            )
        function = self.functions.get(worker.name)
        if function is None or len(function.parameters) != 1:
            return _mir._ErrorValue(
                "KS3914: task worker must be a unary named function"
            )
        if _runtime._contains_capability(argument):
            return _mir._ErrorValue(
                "KS3914: task arguments cannot carry capabilities in v1"
            )
        if isinstance(argument, TaskScopeValue):
            return _mir._ErrorValue(
                "KS3914: task arguments cannot carry TaskScope control handles"
            )
        try:
            return scope.spawn(worker, argument)
        except StructuredTaskError as error:
            return _mir._ErrorValue(str(error))

    if callee.name == "task_join_all":
        if scope.join_result is not None:
            return scope.join_result
        scope.closed = True
        first_failure = None
        for record in scope.records():
            record.state = TASK_RUNNING
            result = _ORIGINAL_INVOKE(self, record.worker, [record.argument])
            failure = result if isinstance(result, _mir._ErrorValue) else None
            if failure is None and result is not _mir._UNIT:
                failure = _mir._ErrorValue("KS3914: task worker must return Void")
            scope.mark_terminal(record, failure)
            if first_failure is None and failure is not None:
                first_failure = failure
        scope.join_result = first_failure if first_failure is not None else _mir._UNIT
        return scope.join_result

    if callee.name == "task_pending":
        return scope.pending
    if callee.name == "task_capacity":
        return scope.capacity
    return scope.closed


def _to_string(value):
    if isinstance(value, TaskScopeValue):
        return str(value)
    return _ORIGINAL_TO_STRING(value)


def install_structured_tasks_mir_v1() -> None:
    global _INSTALLED, _ORIGINAL_INVOKE, _ORIGINAL_TO_STRING
    if _INSTALLED:
        return
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | set(_BUILTINS))
    _ORIGINAL_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _invoke
    _ORIGINAL_TO_STRING = _mir._to_string
    _mir._to_string = _to_string
    _INSTALLED = True
