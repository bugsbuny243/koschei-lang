"""Backend representation alignment for Structured Task Scope v1.

A Koschei function with no declared return type is structurally Void. The legacy
AST interpreter can still expose the value of its final expression statement as
an internal implementation detail, while sealed MIR/native code represents the
same function as unit. Structured tasks must not let that backend detail change
whether a statically proven Void worker succeeds.

This layer therefore treats any non-Error worker completion as successful across
all three runtimes. Non-Void workers remain rejected by Typed HIR before execution.
"""

from __future__ import annotations

from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from .structured_tasks import TASK_RUNNING, TaskScopeValue

_INSTALLED = False
_ORIGINAL_TREE_INVOKE = None
_ORIGINAL_MIR_INVOKE = None

_GO_OLD = '''\t\tif failure, failed := result.(*KsError); failed {
\t\t\tslot.State = ksTaskFailed
\t\t\tslot.Failure = failure
\t\t\tif firstFailure == nil { firstFailure = failure }
\t\t} else {
\t\t\tif _, unit := result.(ksUnitType); !unit {
\t\t\t\tfailure := ksErrorf("KS3914: task worker must return Void")
\t\t\t\tslot.State = ksTaskFailed
\t\t\t\tslot.Failure = failure
\t\t\t\tif firstFailure == nil { firstFailure = failure }
\t\t\t} else {
\t\t\t\tslot.State = ksTaskDone
\t\t\t}
\t\t}
'''

_GO_NEW = '''\t\tif failure, failed := result.(*KsError); failed {
\t\t\tslot.State = ksTaskFailed
\t\t\tslot.Failure = failure
\t\t\tif firstFailure == nil { firstFailure = failure }
\t\t} else {
\t\t\t// Typed HIR already proved the worker is Void. Runtime success is
\t\t\t// therefore every non-Error completion; do not depend on an internal
\t\t\t// backend-specific unit representation here.
\t\t\tslot.State = ksTaskDone
\t\t}
'''


def _tree_invoke(self, callee, arguments, location):
    if not (isinstance(callee, str) and callee == "task_join_all"):
        return _ORIGINAL_TREE_INVOKE(self, callee, arguments, location)
    self._require_arity(callee, arguments, 1, location)
    scope = arguments[0]
    if not isinstance(scope, TaskScopeValue):
        return _runtime.KsError("KS3915: task_join_all expects TaskScope")
    if scope.join_result is not None:
        return scope.join_result

    scope.closed = True
    first_failure = None
    for record in scope.records():
        record.state = TASK_RUNNING
        try:
            result = _ORIGINAL_TREE_INVOKE(
                self,
                record.worker,
                [record.argument],
                location,
            )
            failure = result if isinstance(result, _runtime.KsError) else None
        except _runtime.KoscheiRuntimeError as error:
            failure = _runtime.KsError(f"{error.code}: {error.message}")
        scope.mark_terminal(record, failure)
        if first_failure is None and failure is not None:
            first_failure = failure
    scope.join_result = first_failure if first_failure is not None else _runtime.KsUnit
    return scope.join_result


def _mir_invoke(self, callee, arguments):
    if not (
        isinstance(callee, _mir._BuiltinRef)
        and callee.name == "task_join_all"
    ):
        return _ORIGINAL_MIR_INVOKE(self, callee, arguments)
    if len(arguments) != 1:
        raise _mir.MirNativeRuntimeError("task_join_all expects 1 arguments")
    scope = arguments[0]
    if not isinstance(scope, TaskScopeValue):
        return _mir._ErrorValue("KS3915: task_join_all expects TaskScope")
    if scope.join_result is not None:
        return scope.join_result

    scope.closed = True
    first_failure = None
    for record in scope.records():
        record.state = TASK_RUNNING
        result = _ORIGINAL_MIR_INVOKE(self, record.worker, [record.argument])
        failure = result if isinstance(result, _mir._ErrorValue) else None
        scope.mark_terminal(record, failure)
        if first_failure is None and failure is not None:
            first_failure = failure
    scope.join_result = first_failure if first_failure is not None else _mir._UNIT
    return scope.join_result


def install_structured_tasks_runtime_alignment() -> None:
    global _INSTALLED, _ORIGINAL_TREE_INVOKE, _ORIGINAL_MIR_INVOKE
    if _INSTALLED:
        return

    _ORIGINAL_TREE_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _tree_invoke

    _ORIGINAL_MIR_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke

    if _GO_OLD in _codegen.RUNTIME_PRELUDE:
        _codegen.RUNTIME_PRELUDE = _codegen.RUNTIME_PRELUDE.replace(
            _GO_OLD,
            _GO_NEW,
            1,
        )
    elif _GO_NEW not in _codegen.RUNTIME_PRELUDE:
        raise RuntimeError(
            "Structured Task Scope Go runtime layout changed; alignment must fail closed."
        )

    _INSTALLED = True
