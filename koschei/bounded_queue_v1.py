"""Language ABI for fixed-capacity FIFO queues and explicit backpressure."""

from __future__ import annotations

from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import type_contracts as _contracts
from . import typed_hir as _typed_hir
from .ast_nodes import CallExpression, Identifier
from .bounded_queue import (
    MAX_QUEUE_CAPACITY,
    MIN_QUEUE_CAPACITY,
    BoundedQueueError,
    BoundedQueueValue,
)
from .type_system import (
    BOOL,
    ERROR,
    INT,
    GenericType,
    TypeNode,
    UnionType,
    UnknownType,
    generic,
    parse_type_text,
    render_type,
    union_type,
)

_QUEUE = "BoundedQueue"
_BUILTINS = {
    "bounded_queue",
    "queue_try_send",
    "queue_try_recv",
    "queue_len",
    "queue_capacity",
}
_FALLIBLE = {"bounded_queue", "queue_try_recv"}
_INSTALLED = False
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_VALIDATE_GENERIC = None
_ORIGINAL_TYPED_CALL_TYPE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_CALL = None


_GO_RUNTIME = rf'''
const ksQueueMinCapacity int64 = {MIN_QUEUE_CAPACITY}
const ksQueueMaxCapacity int64 = {MAX_QUEUE_CAPACITY}

type KsBoundedQueue struct {{
	Capacity int64
	ItemTag string
	Buffer []any
	Head int64
	Tail int64
	Count int64
}}

func (q *KsBoundedQueue) String() string {{
	return fmt.Sprintf("BoundedQueue(len=%d, capacity=%d)", q.Count, q.Capacity)
}}

func ksQueueTypeTag(value any) string {{
	switch item := value.(type) {{
	case bool:
		return "Bool"
	case int64:
		return "Int"
	case float64:
		return "Float"
	case string:
		return "String"
	case ksUnitType:
		return "Void"
	case *KsError:
		return "Error"
	case *KsStruct:
		return "Struct:" + item.TypeName
	case *KsEnum:
		return "Enum:" + item.EnumName
	case []any:
		return "List"
	case *KsMap:
		return "Map"
	case *KsBoundedQueue:
		return "BoundedQueue:" + item.ItemTag
	default:
		return fmt.Sprintf("%T", value)
	}}
}}

func ksBoundedQueue(capacityValue any, witness any) any {{
	capacity, ok := capacityValue.(int64)
	if !ok {{
		return ksErrorf("KS3901: bounded_queue capacity must be Int")
	}}
	if capacity < ksQueueMinCapacity || capacity > ksQueueMaxCapacity {{
		return ksErrorf("KS3901: bounded_queue capacity must be between 1 and 65536")
	}}
	if ksContainsCapability(witness) {{
		return ksErrorf("KS3904: capability values cannot be bounded-queue item types")
	}}
	return &KsBoundedQueue{{
		Capacity: capacity,
		ItemTag: ksQueueTypeTag(witness),
		Buffer: make([]any, int(capacity)),
	}}
}}

func ksQueueTrySend(queueValue any, value any) any {{
	queue, ok := queueValue.(*KsBoundedQueue)
	if !ok {{
		return ksErrorf("KS3902: queue_try_send expects BoundedQueue")
	}}
	if ksContainsCapability(value) {{
		return ksErrorf("KS3904: capability values cannot enter a bounded queue")
	}}
	if ksQueueTypeTag(value) != queue.ItemTag {{
		return ksErrorf("KS3904: bounded-queue runtime item type mismatch")
	}}
	if queue.Count == queue.Capacity {{
		return false
	}}
	queue.Buffer[int(queue.Tail)] = value
	queue.Tail = (queue.Tail + 1) % queue.Capacity
	queue.Count++
	return true
}}

func ksQueueTryRecv(queueValue any) any {{
	queue, ok := queueValue.(*KsBoundedQueue)
	if !ok {{
		return ksErrorf("KS3902: queue_try_recv expects BoundedQueue")
	}}
	if queue.Count == 0 {{
		return ksErrorf("KS3903: bounded queue is empty")
	}}
	value := queue.Buffer[int(queue.Head)]
	queue.Buffer[int(queue.Head)] = nil
	queue.Head = (queue.Head + 1) % queue.Capacity
	queue.Count--
	return value
}}

func ksQueueLen(queueValue any) any {{
	queue, ok := queueValue.(*KsBoundedQueue)
	if !ok {{
		return ksErrorf("KS3902: queue_len expects BoundedQueue")
	}}
	return queue.Count
}}

func ksQueueCapacity(queueValue any) any {{
	queue, ok := queueValue.(*KsBoundedQueue)
	if !ok {{
		return ksErrorf("KS3902: queue_capacity expects BoundedQueue")
	}}
	return queue.Capacity
}}
'''


def _queue_item(type_node: TypeNode, location, *, subject: str) -> TypeNode:
    if not isinstance(type_node, GenericType) or type_node.name != _QUEUE:
        raise _semantic.SemanticError(
            "KS1301",
            f"{subject} BoundedQueue<T> bekler, {render_type(type_node)} bulundu.",
            location,
        )
    if len(type_node.arguments) != 1 or isinstance(type_node.arguments[0], UnknownType):
        raise _semantic.SemanticError(
            "KS3904",
            f"{subject}: queue item tipi somut olmalıdır.",
            location,
        )
    return type_node.arguments[0]


def _legacy_queue_item(type_name: str | None, location, *, subject: str) -> str:
    if not type_name:
        raise _semantic.SemanticError("KS3904", f"{subject}: queue tipi bilinmiyor.", location)
    try:
        node = parse_type_text(type_name)
    except ValueError as error:
        raise _semantic.SemanticError("KS1301", str(error), location) from error
    item = _queue_item(node, location, subject=subject)
    return render_type(item)


def _semantic_expression(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        name = expression.callee.name
        actual = [self._check_expression(item) for item in expression.arguments]
        expected_arity = {
            "bounded_queue": 2,
            "queue_try_send": 2,
            "queue_try_recv": 1,
            "queue_len": 1,
            "queue_capacity": 1,
        }[name]
        if len(actual) != expected_arity:
            raise _semantic.SemanticError(
                "KS1301",
                f"{name}() {expected_arity} argüman bekler, {len(actual)} verildi.",
                expression.location,
            )
        if name == "bounded_queue":
            self._require_assignable(("Int",), actual[0], "bounded_queue() kapasitesi", expression.location)
            witness = actual[1]
            if witness in {None, "_"}:
                raise _semantic.SemanticError(
                    "KS3904", "bounded_queue() type witness somut bir tip sağlamalıdır.", expression.location
                )
            if self._types_are_sensitive(self._type_names(witness)):
                raise _semantic.SemanticError(
                    "KS2402", "Capability tipi bounded queue içinde saklanamaz.", expression.location
                )
            return f"BoundedQueue<{witness}> or Error"

        item_type = _legacy_queue_item(actual[0], expression.location, subject=f"{name}()")
        if name == "queue_try_send":
            self._require_assignable((item_type,), actual[1], "queue_try_send() değeri", expression.location)
            return "Bool"
        if name == "queue_try_recv":
            return f"{item_type} or Error"
        return "Int"
    return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)


def _semantic_fallible(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name in _FALLIBLE
    ):
        return True
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _validate_generic(self, type_name, location):
    try:
        node = parse_type_text(type_name)
    except ValueError:
        return _ORIGINAL_VALIDATE_GENERIC(self, type_name, location)
    if isinstance(node, GenericType) and node.name == _QUEUE:
        if len(node.arguments) != 1:
            raise _semantic.SemanticError(
                "KS1301", "BoundedQueue 1 tip argümanı bekler.", location
            )
        inner = render_type(node.arguments[0])
        _ORIGINAL_VALIDATE_GENERIC(self, inner, location)
        if self._types_are_sensitive(self._type_names(inner)):
            raise _semantic.SemanticError(
                "KS2402", "Capability tipi BoundedQueue generic argümanı olamaz.", location
            )
        return
    if getattr(node, "name", None) == _QUEUE:
        raise _semantic.SemanticError(
            "KS1301", "BoundedQueue tipi BoundedQueue<T> biçiminde kullanılmalıdır.", location
        )
    return _ORIGINAL_VALIDATE_GENERIC(self, type_name, location)


def _typed_call_type(self, name, arguments, location):
    if name not in _BUILTINS:
        return _ORIGINAL_TYPED_CALL_TYPE(self, name, arguments, location)
    expected_arity = {
        "bounded_queue": 2,
        "queue_try_send": 2,
        "queue_try_recv": 1,
        "queue_len": 1,
        "queue_capacity": 1,
    }[name]
    if len(arguments) != expected_arity:
        raise _semantic.SemanticError(
            "KS1301",
            f"{name}() {expected_arity} argüman bekler, {len(arguments)} verildi.",
            location,
        )
    if name == "bounded_queue":
        _contracts.require_assignable(INT, arguments[0], "bounded_queue() kapasitesi", location)
        witness = arguments[1]
        if isinstance(witness, UnknownType) or isinstance(witness, UnionType):
            raise _semantic.SemanticError(
                "KS3904", "bounded_queue() type witness tek ve somut bir tip olmalıdır.", location
            )
        if self.contracts.is_sensitive(witness):
            raise _semantic.SemanticError(
                "KS2402", "Capability tipi bounded queue içinde saklanamaz.", location
            )
        self.contracts.validate_type(witness, location, "bounded_queue() type witness")
        return union_type(generic(_QUEUE, witness), ERROR)

    item = _queue_item(arguments[0], location, subject=f"{name}()")
    if name == "queue_try_send":
        _contracts.require_assignable(item, arguments[1], "queue_try_send() değeri", location)
        return BOOL
    if name == "queue_try_recv":
        return union_type(item, ERROR)
    return INT


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name in _BUILTINS:
        return expression.name
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_invoke(self, callee, arguments, location):
    if not (isinstance(callee, str) and callee in _BUILTINS):
        return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)
    expected = {
        "bounded_queue": 2,
        "queue_try_send": 2,
        "queue_try_recv": 1,
        "queue_len": 1,
        "queue_capacity": 1,
    }[callee]
    self._require_arity(callee, arguments, expected, location)
    if callee == "bounded_queue":
        capacity, witness = arguments
        if _runtime._contains_capability(witness):
            raise _runtime.KoscheiRuntimeError(
                "KS3904", "Capability value cannot be a bounded-queue item type.", location
            )
        try:
            return BoundedQueueValue(capacity, _alignment._runtime_type_node(witness))
        except BoundedQueueError as error:
            return _runtime.KsError(str(error))

    queue = arguments[0]
    if not isinstance(queue, BoundedQueueValue):
        return _runtime.KsError(f"KS3902: {callee} expects BoundedQueue")
    if callee == "queue_try_send":
        value = arguments[1]
        if _runtime._contains_capability(value):
            raise _runtime.KoscheiRuntimeError(
                "KS3904", "Capability value cannot enter a bounded queue.", location
            )
        if not _alignment._matches_node(value, queue.item_type):
            raise _runtime.KoscheiRuntimeError(
                "KS3904",
                "bounded-queue runtime item type mismatch: expected "
                + render_type(queue.item_type),
                location,
            )
        return queue.try_send(value)
    if callee == "queue_try_recv":
        ok, value = queue.try_recv()
        return value if ok else _runtime.KsError("KS3903: bounded queue is empty")
    if callee == "queue_len":
        return queue.length
    return queue.capacity


def _runtime_type_node(value):
    if isinstance(value, BoundedQueueValue):
        return generic(_QUEUE, value.item_type)
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _codegen_call(self, expression, depth):
    if (
        isinstance(expression.callee, Identifier)
        and expression.callee.name in _BUILTINS
    ):
        name = expression.callee.name
        prelude: list[str] = []
        arguments: list[str] = []
        for argument in expression.arguments:
            value, argument_prelude = self._expression(argument, depth)
            prelude.extend(argument_prelude)
            arguments.append(value)
        expected = {
            "bounded_queue": 2,
            "queue_try_send": 2,
            "queue_try_recv": 1,
            "queue_len": 1,
            "queue_capacity": 1,
        }[name]
        self._check_arity(name, arguments, expected, expression.location)
        helper = {
            "bounded_queue": "ksBoundedQueue",
            "queue_try_send": "ksQueueTrySend",
            "queue_try_recv": "ksQueueTryRecv",
            "queue_len": "ksQueueLen",
            "queue_capacity": "ksQueueCapacity",
        }[name]
        return f"{helper}({', '.join(arguments)})", prelude
    return _ORIGINAL_CODEGEN_CALL(self, expression, depth)


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    entries = {
        "KS3901": ("Geçersiz bounded queue kapasitesi", "Invalid bounded queue capacity"),
        "KS3902": ("Bounded queue değeri bekleniyordu", "Bounded queue value required"),
        "KS3903": ("Bounded queue boş", "Bounded queue is empty"),
        "KS3904": ("Bounded queue tip bütünlüğü ihlali", "Bounded queue type-integrity violation"),
    }
    for code, (tr, en) in entries.items():
        CATALOG[code] = Diagnostic(
            code,
            tr,
            tr + ".",
            "Bounded queue/backpressure sözleşmesi fail-closed korundu.",
            "Kapasiteyi veya queue item tipini düzeltin; full/empty durumlarını açıkça ele alın.",
            "let q = bounded_queue(64, 0) or return",
        )
        ENGLISH_CATALOG[code] = Diagnostic(
            code,
            en,
            en + ".",
            "The bounded queue/backpressure contract failed closed.",
            "Fix the capacity or queue item type and handle full/empty states explicitly.",
            "let q = bounded_queue(64, 0) or return",
        )


def install_bounded_queue_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_SEMANTIC_EXPRESSION, _ORIGINAL_SEMANTIC_FALLIBLE
    global _ORIGINAL_VALIDATE_GENERIC, _ORIGINAL_TYPED_CALL_TYPE
    global _ORIGINAL_RUNTIME_EVALUATE, _ORIGINAL_RUNTIME_INVOKE
    global _ORIGINAL_RUNTIME_TYPE_NODE, _ORIGINAL_CODEGEN_CALL
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.update(_BUILTINS)
    _contracts.GENERIC_ARITY[_QUEUE] = 1
    _contracts.CONTAINER_NAMES.add(_QUEUE)
    _contracts.RESERVED_TYPE_PARAMETERS.add(_QUEUE)

    _ORIGINAL_SEMANTIC_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINAL_SEMANTIC_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible
    _ORIGINAL_VALIDATE_GENERIC = _semantic.SemanticChecker._validate_generic_type
    _semantic.SemanticChecker._validate_generic_type = _validate_generic

    _ORIGINAL_TYPED_CALL_TYPE = _typed_hir.TypedHIRChecker.call_type
    _typed_hir.TypedHIRChecker.call_type = _typed_call_type

    _ORIGINAL_RUNTIME_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINAL_RUNTIME_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke
    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node

    _ORIGINAL_CODEGEN_CALL = _codegen.GoCodegen._call
    _codegen.GoCodegen._call = _codegen_call
    if "type KsBoundedQueue struct" not in _codegen.RUNTIME_PRELUDE:
        _codegen.RUNTIME_PRELUDE += "\n" + _GO_RUNTIME
    _register_diagnostics()
    _INSTALLED = True
