"""Cancellation and share-safe ownership gate for Structured Task Scope v1.

This layer is installed after the base task-scope/runtime-alignment bridges. It
adds deterministic cancellation and narrows the task argument boundary so a
future parallel executor cannot inherit arbitrary mutable aliasing by accident.
"""

from __future__ import annotations

from . import _typed_expr as _typed_expr_module
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from . import semantic as _semantic
from . import type_contracts as _contracts
from .ast_nodes import CallExpression, Identifier
from .bounded_queue import BoundedQueueValue
from .structured_tasks import (
    TASK_CANCELLED,
    TASK_RUNNING,
    StructuredTaskError,
    TaskScopeValue,
)
from .type_system import (
    BOOL,
    ERROR,
    INT,
    GenericType,
    NamedType,
    TypeNode,
    UnionType,
    union_type,
)

_CANCEL_BUILTINS = {"task_cancel", "task_cancel_all"}
_FALLIBLE = _CANCEL_BUILTINS
_SAFE_SCALARS = {"Bool", "Int", "Float", "String"}
_INSTALLED = False
_ORIGINAL_TYPED_INFER = None
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_TREE_INVOKE = None
_ORIGINAL_MIR_INVOKE = None
_ORIGINAL_CODEGEN_CALL = None

_GO_STATE_OLD = '''const (
\tksTaskStatePending int64 = iota
\tksTaskStateRunning
\tksTaskStateDone
\tksTaskStateFailed
)
'''

_GO_STATE_NEW = '''const (
\tksTaskStatePending int64 = iota
\tksTaskStateRunning
\tksTaskStateDone
\tksTaskStateFailed
\tksTaskStateCancelled
)
'''

_GO_SAFETY_HELPERS = r'''
func ksTaskArgumentShareSafe(value any) bool {
\tswitch item := value.(type) {
\tcase bool, int64, float64, string:
\t\treturn true
\tcase *KsBoundedQueue:
\t\tswitch item.ItemTag {
\t\tcase "Bool", "Int", "Float", "String":
\t\t\treturn true
\t\tdefault:
\t\t\treturn false
\t\t}
\tdefault:
\t\treturn false
\t}
}

func ksTaskCancel(scopeValue any, taskIDValue any) any {
\tscope, ok := scopeValue.(*KsTaskScope)
\tif !ok {
\t\treturn ksErrorf("KS3915: task_cancel expects TaskScope")
\t}
\tif scope.Closed {
\t\treturn ksErrorf("KS3913: task scope is already closed")
\t}
\ttaskID, ok := taskIDValue.(int64)
\tif !ok || taskID < 0 || taskID >= scope.Count {
\t\treturn ksErrorf("KS3916: task id is outside this scope")
\t}
\tslot := &scope.Slots[int(taskID)]
\tif slot.State == ksTaskStateCancelled {
\t\treturn false
\t}
\tif slot.State != ksTaskStatePending {
\t\treturn false
\t}
\tslot.State = ksTaskStateCancelled
\tscope.Terminal++
\treturn true
}

func ksTaskCancelAll(scopeValue any) any {
\tscope, ok := scopeValue.(*KsTaskScope)
\tif !ok {
\t\treturn ksErrorf("KS3915: task_cancel_all expects TaskScope")
\t}
\tif scope.Closed {
\t\treturn ksErrorf("KS3913: task scope is already closed")
\t}
\tcancelled := int64(0)
\tfor index := int64(0); index < scope.Count; index++ {
\t\tslot := &scope.Slots[int(index)]
\t\tif slot.State == ksTaskStatePending {
\t\t\tslot.State = ksTaskStateCancelled
\t\t\tscope.Terminal++
\t\t\tcancelled++
\t\t}
\t}
\treturn cancelled
}

'''


def _is_share_safe_type(type_node: TypeNode) -> bool:
    if isinstance(type_node, NamedType):
        return type_node.name in _SAFE_SCALARS
    if isinstance(type_node, GenericType) and type_node.name == "BoundedQueue":
        if len(type_node.arguments) != 1:
            return False
        item = type_node.arguments[0]
        return isinstance(item, NamedType) and item.name in _SAFE_SCALARS
    return False


def _typed_spawn(checker, expression):
    if len(expression.arguments) != 3:
        raise _semantic.SemanticError(
            "KS1301",
            f"task_spawn() 3 argüman bekler, {len(expression.arguments)} verildi.",
            expression.location,
        )
    scope_type = checker.infer(expression.arguments[0])
    _contracts.require_assignable(
        NamedType("TaskScope"),
        scope_type,
        "task_spawn() scope",
        expression.location,
    )

    worker_expression = expression.arguments[1]
    if not isinstance(worker_expression, Identifier):
        raise _semantic.SemanticError(
            "KS3914",
            "task_spawn() worker doğrudan named function olmalıdır.",
            worker_expression.location,
        )
    worker = checker.functions.get(worker_expression.name)
    if worker is None or worker.name == "main":
        raise _semantic.SemanticError(
            "KS3914",
            "task_spawn() worker yerel, named ve main dışı bir fonksiyon olmalıdır.",
            worker_expression.location,
        )
    if len(worker.parameters) != 1:
        raise _semantic.SemanticError(
            "KS3914",
            "task worker tam olarak 1 parametre almalıdır.",
            worker.location,
        )
    if worker.return_type is not None:
        raise _semantic.SemanticError(
            "KS3914",
            "task worker v1'de Void dönmelidir; task sonucu sessizce atılamaz.",
            worker.return_type.location,
        )

    checker.infer(worker_expression)
    parameter_type = _contracts.function_type(worker, worker.parameters[0].type_ref)
    checker.contracts.validate_type(
        parameter_type,
        worker.parameters[0].location,
        f"task worker '{worker.name}' parametresi",
    )
    if checker.contracts.is_sensitive(parameter_type):
        raise _semantic.SemanticError(
            "KS3914",
            "task worker capability parametresi alamaz; v1 task authority-free'dur.",
            worker.parameters[0].location,
        )
    if not _is_share_safe_type(parameter_type):
        raise _semantic.SemanticError(
            "KS3917",
            "task worker parametresi share-safe scalar veya BoundedQueue<scalar> olmalıdır.",
            worker.parameters[0].location,
        )

    argument_type = checker.infer(expression.arguments[2])
    if checker.contracts.is_sensitive(argument_type):
        raise _semantic.SemanticError(
            "KS3914",
            "task argümanı capability taşıyamaz.",
            expression.arguments[2].location,
        )
    if not _is_share_safe_type(argument_type):
        raise _semantic.SemanticError(
            "KS3917",
            "task argümanı share-safe scalar veya BoundedQueue<scalar> olmalıdır.",
            expression.arguments[2].location,
        )
    _contracts.require_assignable(
        parameter_type,
        argument_type,
        f"task worker '{worker.name}' argümanı",
        expression.arguments[2].location,
    )
    return checker.record(expression, union_type(INT, ERROR))


def _typed_infer(checker, expression):
    if not (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
    ):
        return _ORIGINAL_TYPED_INFER(checker, expression)
    name = expression.callee.name
    if name == "task_spawn":
        return _typed_spawn(checker, expression)
    if name not in _CANCEL_BUILTINS:
        return _ORIGINAL_TYPED_INFER(checker, expression)

    expected = 2 if name == "task_cancel" else 1
    if len(expression.arguments) != expected:
        raise _semantic.SemanticError(
            "KS1301",
            f"{name}() {expected} argüman bekler, {len(expression.arguments)} verildi.",
            expression.location,
        )
    scope_type = checker.infer(expression.arguments[0])
    _contracts.require_assignable(
        NamedType("TaskScope"), scope_type, f"{name}() scope", expression.location
    )
    if name == "task_cancel":
        task_id = checker.infer(expression.arguments[1])
        _contracts.require_assignable(
            INT, task_id, "task_cancel() task id", expression.arguments[1].location
        )
        return checker.record(expression, union_type(BOOL, ERROR))
    return checker.record(expression, union_type(INT, ERROR))


def _semantic_expression(self, expression):
    if not (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _CANCEL_BUILTINS
    ):
        return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)
    name = expression.callee.name
    expected = 2 if name == "task_cancel" else 1
    if len(expression.arguments) != expected:
        raise _semantic.SemanticError(
            "KS1301",
            f"{name}() {expected} argüman bekler, {len(expression.arguments)} verildi.",
            expression.location,
        )
    self._check_expression(expression.arguments[0])
    if name == "task_cancel":
        task_id = self._check_expression(expression.arguments[1])
        self._require_assignable(("Int",), task_id, "task_cancel() task id", expression.location)
        return "Bool or Error"
    return "Int or Error"


def _semantic_fallible(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _FALLIBLE
    ):
        return True
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _is_share_safe_value(value) -> bool:
    if type(value) in {bool, int, float, str}:
        return True
    if isinstance(value, BoundedQueueValue):
        item_type = value.item_type
        return isinstance(item_type, NamedType) and item_type.name in _SAFE_SCALARS
    return False


def _tree_invoke(self, callee, arguments, location):
    if not isinstance(callee, str):
        return _ORIGINAL_TREE_INVOKE(self, callee, arguments, location)

    if callee == "task_spawn":
        self._require_arity(callee, arguments, 3, location)
        argument = arguments[2]
        if _runtime._contains_capability(argument):
            return _ORIGINAL_TREE_INVOKE(self, callee, arguments, location)
        if not _is_share_safe_value(argument):
            return _runtime.KsError(
                "KS3917: task argument is not share-safe in structured task v1"
            )
        return _ORIGINAL_TREE_INVOKE(self, callee, arguments, location)

    if callee == "task_cancel":
        self._require_arity(callee, arguments, 2, location)
        scope = arguments[0]
        if not isinstance(scope, TaskScopeValue):
            return _runtime.KsError("KS3915: task_cancel expects TaskScope")
        try:
            return scope.cancel(arguments[1])
        except StructuredTaskError as error:
            return _runtime.KsError(str(error))

    if callee == "task_cancel_all":
        self._require_arity(callee, arguments, 1, location)
        scope = arguments[0]
        if not isinstance(scope, TaskScopeValue):
            return _runtime.KsError("KS3915: task_cancel_all expects TaskScope")
        try:
            return scope.cancel_all()
        except StructuredTaskError as error:
            return _runtime.KsError(str(error))

    if callee != "task_join_all":
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
        if record.state == TASK_CANCELLED:
            continue
        record.state = TASK_RUNNING
        try:
            result = _ORIGINAL_TREE_INVOKE(self, record.worker, [record.argument], location)
            failure = result if isinstance(result, _runtime.KsError) else None
        except _runtime.KoscheiRuntimeError as error:
            failure = _runtime.KsError(f"{error.code}: {error.message}")
        scope.mark_terminal(record, failure)
        if first_failure is None and failure is not None:
            first_failure = failure
    scope.join_result = first_failure if first_failure is not None else _runtime.KsUnit
    return scope.join_result


def _mir_invoke(self, callee, arguments):
    if not isinstance(callee, _mir._BuiltinRef):
        return _ORIGINAL_MIR_INVOKE(self, callee, arguments)
    name = callee.name

    if name == "task_spawn":
        if len(arguments) != 3:
            raise _mir.MirNativeRuntimeError("task_spawn expects 3 arguments")
        argument = arguments[2]
        if _runtime._contains_capability(argument):
            return _ORIGINAL_MIR_INVOKE(self, callee, arguments)
        if not _is_share_safe_value(argument):
            return _mir._ErrorValue(
                "KS3917: task argument is not share-safe in structured task v1"
            )
        return _ORIGINAL_MIR_INVOKE(self, callee, arguments)

    if name == "task_cancel":
        if len(arguments) != 2:
            raise _mir.MirNativeRuntimeError("task_cancel expects 2 arguments")
        scope = arguments[0]
        if not isinstance(scope, TaskScopeValue):
            return _mir._ErrorValue("KS3915: task_cancel expects TaskScope")
        try:
            return scope.cancel(arguments[1])
        except StructuredTaskError as error:
            return _mir._ErrorValue(str(error))

    if name == "task_cancel_all":
        if len(arguments) != 1:
            raise _mir.MirNativeRuntimeError("task_cancel_all expects 1 arguments")
        scope = arguments[0]
        if not isinstance(scope, TaskScopeValue):
            return _mir._ErrorValue("KS3915: task_cancel_all expects TaskScope")
        try:
            return scope.cancel_all()
        except StructuredTaskError as error:
            return _mir._ErrorValue(str(error))

    if name != "task_join_all":
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
        if record.state == TASK_CANCELLED:
            continue
        record.state = TASK_RUNNING
        result = _ORIGINAL_MIR_INVOKE(self, record.worker, [record.argument])
        failure = result if isinstance(result, _mir._ErrorValue) else None
        scope.mark_terminal(record, failure)
        if first_failure is None and failure is not None:
            first_failure = failure
    scope.join_result = first_failure if first_failure is not None else _mir._UNIT
    return scope.join_result


def _codegen_call(self, expression, depth):
    if not (
        isinstance(expression.callee, Identifier)
        and expression.callee.name in _CANCEL_BUILTINS
    ):
        return _ORIGINAL_CODEGEN_CALL(self, expression, depth)
    name = expression.callee.name
    expected = 2 if name == "task_cancel" else 1
    prelude: list[str] = []
    arguments: list[str] = []
    for argument in expression.arguments:
        value, item_prelude = self._expression(argument, depth)
        prelude.extend(item_prelude)
        arguments.append(value)
    self._check_arity(name, arguments, expected, expression.location)
    helper = "ksTaskCancel" if name == "task_cancel" else "ksTaskCancelAll"
    return f"{helper}({', '.join(arguments)})", prelude


def _patch_go_runtime() -> None:
    prelude = _codegen.RUNTIME_PRELUDE
    if _GO_STATE_OLD in prelude:
        prelude = prelude.replace(_GO_STATE_OLD, _GO_STATE_NEW, 1)
    elif _GO_STATE_NEW not in prelude:
        raise RuntimeError("Structured task Go state layout changed; safety patch failed closed.")

    marker = "func ksTaskSpawn(scopeValue any, workerValue any, argument any) any {"
    if _GO_SAFETY_HELPERS not in prelude:
        if marker not in prelude:
            raise RuntimeError("Structured task Go spawn layout changed; safety patch failed closed.")
        prelude = prelude.replace(marker, _GO_SAFETY_HELPERS + marker, 1)

    spawn_old = '''\tif ksContainsTaskScope(argument) {
\t\treturn ksErrorf("KS3914: task arguments cannot carry TaskScope control handles")
\t}
\tid := scope.Count
'''
    spawn_new = '''\tif ksContainsTaskScope(argument) {
\t\treturn ksErrorf("KS3914: task arguments cannot carry TaskScope control handles")
\t}
\tif !ksTaskArgumentShareSafe(argument) {
\t\treturn ksErrorf("KS3917: task argument is not share-safe in structured task v1")
\t}
\tid := scope.Count
'''
    if spawn_old in prelude:
        prelude = prelude.replace(spawn_old, spawn_new, 1)
    elif spawn_new not in prelude:
        raise RuntimeError("Structured task Go spawn guard changed; safety patch failed closed.")

    join_old = '''\t\tslot := &scope.Slots[int(index)]
\t\tslot.State = ksTaskStateRunning
'''
    join_new = '''\t\tslot := &scope.Slots[int(index)]
\t\tif slot.State == ksTaskStateCancelled {
\t\t\tcontinue
\t\t}
\t\tslot.State = ksTaskStateRunning
'''
    if join_old in prelude:
        prelude = prelude.replace(join_old, join_new, 1)
    elif join_new not in prelude:
        raise RuntimeError("Structured task Go join layout changed; safety patch failed closed.")

    _codegen.RUNTIME_PRELUDE = prelude


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    CATALOG["KS3916"] = Diagnostic(
        "KS3916",
        "Geçersiz task kimliği",
        "Task kimliği bu scope içinde mevcut değil.",
        "Yanlış scope veya task id kullanımı fail-closed reddedildi.",
        "task_spawn() tarafından dönen id'yi aynı scope ile kullanın.",
        "let id = task_spawn(scope, worker, 1) or return",
    )
    ENGLISH_CATALOG["KS3916"] = Diagnostic(
        "KS3916",
        "Invalid task id",
        "The task id does not exist in this scope.",
        "A wrong scope/task-id pair was rejected fail-closed.",
        "Use the id returned by task_spawn() with the same scope.",
        "let id = task_spawn(scope, worker, 1) or return",
    )
    CATALOG["KS3917"] = Diagnostic(
        "KS3917",
        "Task argümanı share-safe değil",
        "Task boundary rastgele mutable alias paylaşımını kabul etmez.",
        "Future parallel yürütme için ownership sınırı korunuyor.",
        "Scalar veya BoundedQueue<scalar> ile iletişim kurun.",
        "task_spawn(scope, worker, queue) or return",
    )
    ENGLISH_CATALOG["KS3917"] = Diagnostic(
        "KS3917",
        "Task argument is not share-safe",
        "The task boundary does not accept arbitrary mutable aliases.",
        "The ownership boundary is preserved for a future parallel executor.",
        "Use a scalar or BoundedQueue<scalar> for communication.",
        "task_spawn(scope, worker, queue) or return",
    )


def install_structured_task_safety_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_TYPED_INFER, _ORIGINAL_SEMANTIC_EXPRESSION
    global _ORIGINAL_SEMANTIC_FALLIBLE, _ORIGINAL_TREE_INVOKE
    global _ORIGINAL_MIR_INVOKE, _ORIGINAL_CODEGEN_CALL
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(_CANCEL_BUILTINS)
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | _CANCEL_BUILTINS)

    _ORIGINAL_TYPED_INFER = _typed_expr_module.infer_expression
    _typed_expr_module.infer_expression = _typed_infer
    _ORIGINAL_SEMANTIC_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINAL_SEMANTIC_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible

    _ORIGINAL_TREE_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _tree_invoke
    _ORIGINAL_MIR_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke

    _ORIGINAL_CODEGEN_CALL = _codegen.GoCodegen._call
    _codegen.GoCodegen._call = _codegen_call
    _patch_go_runtime()
    _register_diagnostics()
    _INSTALLED = True
