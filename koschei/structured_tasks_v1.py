"""Language/runtime bridge for deterministic cooperative task scopes."""

from __future__ import annotations

from . import _typed_expr as _typed_expr_module
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import type_contracts as _contracts
from .ast_nodes import CallExpression, Identifier
from .structured_tasks import (
    MAX_TASK_CAPACITY,
    MIN_TASK_CAPACITY,
    TASK_RUNNING,
    StructuredTaskError,
    TaskScopeValue,
)
from .type_system import (
    BOOL,
    ERROR,
    INT,
    VOID,
    GenericType,
    NamedType,
    TypeNode,
    UnionType,
    generic,
    render_type,
    union_type,
)

_BUILTINS = {
    "task_scope",
    "task_spawn",
    "task_join_all",
    "task_pending",
    "task_capacity",
    "task_closed",
}
_FALLIBLE = {"task_scope", "task_spawn", "task_join_all"}
_INSTALLED = False
_ORIGINAL_TYPED_INFER = None
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_CALL = None


_GO_RUNTIME = rf'''
const ksTaskMinCapacity int64 = {MIN_TASK_CAPACITY}
const ksTaskMaxCapacity int64 = {MAX_TASK_CAPACITY}

const (
	ksTaskPending int64 = iota
	ksTaskRunning
	ksTaskDone
	ksTaskFailed
)

type ksTaskSlot struct {{
	Worker func(any) any
	Argument any
	State int64
	Failure *KsError
}}

type KsTaskScope struct {{
	Capacity int64
	Slots []ksTaskSlot
	Count int64
	Terminal int64
	Closed bool
	Joined bool
	JoinResult any
}}

func (s *KsTaskScope) String() string {{
	return fmt.Sprintf(
		"TaskScope(tasks=%d, pending=%d, capacity=%d, closed=%t)",
		s.Count, s.Count-s.Terminal, s.Capacity, s.Closed,
	)
}}

func ksContainsTaskScope(value any) bool {{
	switch item := value.(type) {{
	case *KsTaskScope:
		return true
	case *KsEnum:
		return item.HasPayload && ksContainsTaskScope(item.Payload)
	case []any:
		for _, value := range item {{
			if ksContainsTaskScope(value) {{ return true }}
		}}
	case *KsMap:
		for _, value := range item.Values {{
			if ksContainsTaskScope(value) {{ return true }}
		}}
	case *KsStruct:
		for _, value := range item.Fields {{
			if ksContainsTaskScope(value) {{ return true }}
		}}
	case *KsBoundedQueue:
		for _, value := range item.Buffer {{
			if value != nil && ksContainsTaskScope(value) {{ return true }}
		}}
	}}
	return false
}}

func ksTaskScope(capacityValue any) any {{
	capacity, ok := capacityValue.(int64)
	if !ok {{
		return ksErrorf("KS3911: task scope capacity must be Int")
	}}
	if capacity < ksTaskMinCapacity || capacity > ksTaskMaxCapacity {{
		return ksErrorf("KS3911: task scope capacity must be between 1 and 4096")
	}}
	return &KsTaskScope{{
		Capacity: capacity,
		Slots: make([]ksTaskSlot, int(capacity)),
	}}
}}

func ksTaskSpawn(scopeValue any, workerValue any, argument any) any {{
	scope, ok := scopeValue.(*KsTaskScope)
	if !ok {{
		return ksErrorf("KS3915: task_spawn expects TaskScope")
	}}
	if scope.Closed {{
		return ksErrorf("KS3913: task scope is already closed")
	}}
	if scope.Count >= scope.Capacity {{
		return ksErrorf("KS3912: task scope capacity is exhausted")
	}}
	worker, ok := workerValue.(func(any) any)
	if !ok {{
		return ksErrorf("KS3914: task worker must be a unary named function")
	}}
	if ksContainsCapability(argument) {{
		return ksErrorf("KS3914: task arguments cannot carry capabilities in v1")
	}}
	if ksContainsTaskScope(argument) {{
		return ksErrorf("KS3914: task arguments cannot carry TaskScope control handles")
	}}
	id := scope.Count
	scope.Slots[int(id)] = ksTaskSlot{{
		Worker: worker,
		Argument: argument,
		State: ksTaskPending,
	}}
	scope.Count++
	return id
}}

func ksTaskJoinAll(scopeValue any) any {{
	scope, ok := scopeValue.(*KsTaskScope)
	if !ok {{
		return ksErrorf("KS3915: task_join_all expects TaskScope")
	}}
	if scope.Joined {{
		return scope.JoinResult
	}}
	// Close before executing the first child. Even if a worker somehow obtains an
	// alias, new work cannot extend the lexical task set during join.
	scope.Closed = true
	var firstFailure *KsError
	for index := int64(0); index < scope.Count; index++ {{
		slot := &scope.Slots[int(index)]
		slot.State = ksTaskRunning
		result := slot.Worker(slot.Argument)
		if failure, failed := result.(*KsError); failed {{
			slot.State = ksTaskFailed
			slot.Failure = failure
			if firstFailure == nil {{ firstFailure = failure }}
		}} else {{
			if _, unit := result.(ksUnitType); !unit {{
				failure := ksErrorf("KS3914: task worker must return Void")
				slot.State = ksTaskFailed
				slot.Failure = failure
				if firstFailure == nil {{ firstFailure = failure }}
			}} else {{
				slot.State = ksTaskDone
			}}
		}}
		scope.Terminal++
	}}
	scope.Joined = true
	if firstFailure != nil {{
		scope.JoinResult = firstFailure
		return firstFailure
	}}
	scope.JoinResult = ksUnit
	return ksUnit
}}

func ksTaskPending(scopeValue any) any {{
	scope, ok := scopeValue.(*KsTaskScope)
	if !ok {{ return ksErrorf("KS3915: task_pending expects TaskScope") }}
	return scope.Count - scope.Terminal
}}

func ksTaskCapacity(scopeValue any) any {{
	scope, ok := scopeValue.(*KsTaskScope)
	if !ok {{ return ksErrorf("KS3915: task_capacity expects TaskScope") }}
	return scope.Capacity
}}

func ksTaskClosed(scopeValue any) any {{
	scope, ok := scopeValue.(*KsTaskScope)
	if !ok {{ return ksErrorf("KS3915: task_closed expects TaskScope") }}
	return scope.Closed
}}
'''


def _contains_task_scope_type(type_node: TypeNode) -> bool:
    if isinstance(type_node, NamedType):
        return type_node.name == "TaskScope"
    if isinstance(type_node, GenericType):
        return any(_contains_task_scope_type(item) for item in type_node.arguments)
    if isinstance(type_node, UnionType):
        return any(_contains_task_scope_type(item) for item in type_node.options)
    return False


def _require_scope(type_node: TypeNode, location, subject: str) -> None:
    _contracts.require_assignable(
        NamedType("TaskScope"),
        type_node,
        subject,
        location,
    )


def _typed_infer(checker, expression):
    if not (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        return _ORIGINAL_TYPED_INFER(checker, expression)

    name = expression.callee.name
    expected = {
        "task_scope": 1,
        "task_spawn": 3,
        "task_join_all": 1,
        "task_pending": 1,
        "task_capacity": 1,
        "task_closed": 1,
    }[name]
    if len(expression.arguments) != expected:
        raise _semantic.SemanticError(
            "KS1301",
            f"{name}() {expected} argüman bekler, {len(expression.arguments)} verildi.",
            expression.location,
        )

    if name == "task_scope":
        capacity = checker.infer(expression.arguments[0])
        _contracts.require_assignable(
            INT, capacity, "task_scope() kapasitesi", expression.location
        )
        return checker.record(
            expression,
            union_type(NamedType("TaskScope"), ERROR),
        )

    scope_type = checker.infer(expression.arguments[0])
    _require_scope(scope_type, expression.location, f"{name}() scope")

    if name == "task_spawn":
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

        # Record the function expression, but validate its argument contract from
        # the declaration rather than from the current legacy function-value type.
        checker.infer(worker_expression)
        parameter_type = _contracts.function_type(
            worker, worker.parameters[0].type_ref
        )
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
        if _contains_task_scope_type(parameter_type):
            raise _semantic.SemanticError(
                "KS3914",
                "TaskScope control handle child task argümanı olarak taşınamaz.",
                worker.parameters[0].location,
            )

        argument_type = checker.infer(expression.arguments[2])
        if checker.contracts.is_sensitive(argument_type):
            raise _semantic.SemanticError(
                "KS3914",
                "task argümanı capability taşıyamaz.",
                expression.arguments[2].location,
            )
        if _contains_task_scope_type(argument_type):
            raise _semantic.SemanticError(
                "KS3914",
                "task argümanı TaskScope control handle taşıyamaz.",
                expression.arguments[2].location,
            )
        _contracts.require_assignable(
            parameter_type,
            argument_type,
            f"task worker '{worker.name}' argümanı",
            expression.arguments[2].location,
        )
        return checker.record(expression, union_type(INT, ERROR))

    if name == "task_join_all":
        return checker.record(expression, union_type(VOID, ERROR))
    if name == "task_closed":
        return checker.record(expression, BOOL)
    return checker.record(expression, INT)


def _semantic_expression(self, expression):
    if not (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)

    name = expression.callee.name
    expected = {
        "task_scope": 1,
        "task_spawn": 3,
        "task_join_all": 1,
        "task_pending": 1,
        "task_capacity": 1,
        "task_closed": 1,
    }[name]
    if len(expression.arguments) != expected:
        raise _semantic.SemanticError(
            "KS1301",
            f"{name}() {expected} argüman bekler, {len(expression.arguments)} verildi.",
            expression.location,
        )
    if name == "task_scope":
        capacity = self._check_expression(expression.arguments[0])
        self._require_assignable(("Int",), capacity, "task_scope() kapasitesi", expression.location)
        return "TaskScope or Error"

    self._check_expression(expression.arguments[0])
    if name == "task_spawn":
        worker_expression = expression.arguments[1]
        if not isinstance(worker_expression, Identifier):
            raise _semantic.SemanticError(
                "KS3914", "task_spawn() worker named function olmalıdır.", worker_expression.location
            )
        worker = self.functions.get(worker_expression.name)
        if worker is None or worker.name == "main" or len(worker.parameters) != 1 or worker.return_type is not None:
            raise _semantic.SemanticError(
                "KS3914",
                "task worker yerel, unary ve Void dönüşlü olmalıdır.",
                worker_expression.location,
            )
        self._check_expression(expression.arguments[2])
        return "Int or Error"
    if name == "task_join_all":
        return "Void or Error"
    if name == "task_closed":
        return "Bool"
    return "Int"


def _semantic_fallible(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _FALLIBLE
    ):
        return True
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _contains_task_scope(value) -> bool:
    if isinstance(value, TaskScopeValue):
        return True
    if isinstance(value, list):
        return any(_contains_task_scope(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_task_scope(item) for item in value.values())
    if isinstance(value, _runtime.StructValue):
        return any(_contains_task_scope(item) for item in value.fields.values())
    if isinstance(value, _runtime.EnumValue) and value.payload is not _runtime._NO_PAYLOAD:
        return _contains_task_scope(value.payload)
    try:
        from .bounded_queue import BoundedQueueValue

        if isinstance(value, BoundedQueueValue):
            return any(
                item is not None and _contains_task_scope(item)
                for item in value._buffer
            )
    except ImportError:
        pass
    return False


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in _BUILTINS:
        return expression.name
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if not (isinstance(callee, str) and callee in _BUILTINS):
        return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)

    expected = {
        "task_scope": 1,
        "task_spawn": 3,
        "task_join_all": 1,
        "task_pending": 1,
        "task_capacity": 1,
        "task_closed": 1,
    }[callee]
    self._require_arity(callee, arguments, expected, location)

    if callee == "task_scope":
        try:
            return TaskScopeValue(arguments[0])
        except StructuredTaskError as error:
            return _runtime.KsError(str(error))

    scope = arguments[0]
    if not isinstance(scope, TaskScopeValue):
        return _runtime.KsError(f"KS3915: {callee} expects TaskScope")

    if callee == "task_spawn":
        worker, argument = arguments[1], arguments[2]
        if not hasattr(worker, "parameters") or len(worker.parameters) != 1:
            return _runtime.KsError("KS3914: task worker must be unary named function")
        if getattr(worker, "return_type", None) is not None:
            return _runtime.KsError("KS3914: task worker must return Void")
        if _runtime._contains_capability(argument):
            return _runtime.KsError("KS3914: task arguments cannot carry capabilities in v1")
        if _contains_task_scope(argument):
            return _runtime.KsError("KS3914: task arguments cannot carry TaskScope control handles")
        try:
            return scope.spawn(worker, argument)
        except StructuredTaskError as error:
            return _runtime.KsError(str(error))

    if callee == "task_join_all":
        if scope.join_result is not None:
            return scope.join_result
        scope.closed = True
        first_failure = None
        for record in scope.records():
            record.state = TASK_RUNNING
            try:
                result = _ORIGINAL_RUNTIME_INVOKE(
                    self, record.worker, [record.argument], location
                )
                failure = result if isinstance(result, _runtime.KsError) else None
                if failure is None and result is not _runtime.KsUnit:
                    failure = _runtime.KsError("KS3914: task worker must return Void")
            except _runtime.KoscheiRuntimeError as error:
                failure = _runtime.KsError(f"{error.code}: {error.message}")
            scope.mark_terminal(record, failure)
            if first_failure is None and failure is not None:
                first_failure = failure
        scope.join_result = first_failure if first_failure is not None else _runtime.KsUnit
        return scope.join_result

    if callee == "task_pending":
        return scope.pending
    if callee == "task_capacity":
        return scope.capacity
    return scope.closed


def _runtime_type_node(value):
    if isinstance(value, TaskScopeValue):
        return NamedType("TaskScope")
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _codegen_call(self, expression, depth):
    if not (
        isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        return _ORIGINAL_CODEGEN_CALL(self, expression, depth)
    name = expression.callee.name
    expected = {
        "task_scope": 1,
        "task_spawn": 3,
        "task_join_all": 1,
        "task_pending": 1,
        "task_capacity": 1,
        "task_closed": 1,
    }[name]
    prelude: list[str] = []
    arguments: list[str] = []
    for argument in expression.arguments:
        value, item_prelude = self._expression(argument, depth)
        prelude.extend(item_prelude)
        arguments.append(value)
    self._check_arity(name, arguments, expected, expression.location)
    helper = {
        "task_scope": "ksTaskScope",
        "task_spawn": "ksTaskSpawn",
        "task_join_all": "ksTaskJoinAll",
        "task_pending": "ksTaskPending",
        "task_capacity": "ksTaskCapacity",
        "task_closed": "ksTaskClosed",
    }[name]
    return f"{helper}({', '.join(arguments)})", prelude


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    entries = {
        "KS3911": ("Geçersiz task scope kapasitesi", "Invalid task scope capacity"),
        "KS3912": ("Task scope kapasitesi dolu", "Task scope capacity exhausted"),
        "KS3913": ("Task scope kapalı", "Task scope is closed"),
        "KS3914": ("Task worker sözleşmesi ihlali", "Task worker contract violation"),
        "KS3915": ("Geçersiz task scope durumu", "Invalid task scope state"),
    }
    for code, (tr, en) in entries.items():
        CATALOG[code] = Diagnostic(
            code,
            tr,
            tr + ".",
            "Structured task scope sözleşmesi fail-closed korundu.",
            "Worker imzasını, kapasiteyi veya scope kullanımını düzeltin.",
            "let scope = task_scope(16) or return",
        )
        ENGLISH_CATALOG[code] = Diagnostic(
            code,
            en,
            en + ".",
            "The structured task-scope contract failed closed.",
            "Fix the worker signature, capacity, or scope usage.",
            "let scope = task_scope(16) or return",
        )


def install_structured_tasks_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_TYPED_INFER
    global _ORIGINAL_SEMANTIC_EXPRESSION, _ORIGINAL_SEMANTIC_FALLIBLE
    global _ORIGINAL_RUNTIME_EVALUATE, _ORIGINAL_RUNTIME_INVOKE
    global _ORIGINAL_RUNTIME_TYPE_NODE, _ORIGINAL_CODEGEN_CALL
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(_BUILTINS)
    _contracts.RESERVED_TYPE_PARAMETERS.add("TaskScope")

    _ORIGINAL_TYPED_INFER = _typed_expr_module.infer_expression
    _typed_expr_module.infer_expression = _typed_infer

    _ORIGINAL_SEMANTIC_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINAL_SEMANTIC_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible

    _ORIGINAL_RUNTIME_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINAL_RUNTIME_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke
    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node

    _ORIGINAL_CODEGEN_CALL = _codegen.GoCodegen._call
    _codegen.GoCodegen._call = _codegen_call
    if "type KsTaskScope struct" not in _codegen.RUNTIME_PRELUDE:
        _codegen.RUNTIME_PRELUDE += "\n" + _GO_RUNTIME
    _register_diagnostics()
    _INSTALLED = True
