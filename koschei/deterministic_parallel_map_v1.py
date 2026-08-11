"""Bounded deterministic native parallelism for Koschei.

`parallel_map(List<T>, worker, max_workers) -> List<U> or Error` is the first
parallel execution primitive. The Go backend uses a bounded goroutine pool, but
results and failures are committed by input index so scheduler order is never
observable. The interpreter intentionally executes the same contract
sequentially; language semantics do not depend on a host scheduler.

V1 keeps the worker boundary deliberately narrow: direct local named function,
one scalar parameter, one scalar result, and a leaf/pure body. This prevents
stdout, capabilities, nested task/queue operations, recursion, and nested
function calls from becoming nondeterministic while the parallel runtime is
still young.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from . import _typed_expr as _typed_expr
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import mir_native_runtime as _mir
from . import semantic as _semantic
from .ast_nodes import CallExpression, Identifier, Literal, MemberExpression
from .type_contracts import function_type, require_assignable
from .type_system import ERROR, INT, GenericType, NamedType, TypeNode, UnionType, union_type

_BUILTIN = "parallel_map"
_MIN_WORKERS = 1
_MAX_WORKERS = 64
_SCALAR_NAMES = {"Bool", "Int", "Float", "String"}
_PURE_MEMBER_CALLS = {
    "length",
    "to_int",
    "to_float",
    "contains",
    "trim",
    "split",
    "join",
}
_INSTALLED = False
_ORIGINAL_TYPED_INFER = None
_ORIGINAL_SEMANTIC_EXPRESSION = None
_ORIGINAL_SEMANTIC_FALLIBLE = None
_ORIGINAL_RUNTIME_EVALUATE = None
_ORIGINAL_RUNTIME_INVOKE = None
_ORIGINAL_MIR_INVOKE = None
_ORIGINAL_CODEGEN_CALL = None
_ORIGINAL_GENERATE = None


_GO_HELPERS = r'''
const ksParallelMapMaxWorkers int64 = 64

func ksParallelScalar(value any) bool {
\tswitch value.(type) {
\tcase bool, int64, float64, string:
\t\treturn true
\tdefault:
\t\treturn false
\t}
}

func ksParallelMap(value any, transform any, maxWorkersValue any) any {
\tlist, ok := value.([]any)
\tif !ok {
\t\treturn ksErrorf("KS3921: parallel_map expects List<scalar>")
\t}
\tfunction, ok := transform.(func(any) any)
\tif !ok {
\t\treturn ksErrorf("KS3921: parallel_map expects a direct unary worker")
\t}
\tmaxWorkers, ok := maxWorkersValue.(int64)
\tif !ok || maxWorkers < 1 || maxWorkers > ksParallelMapMaxWorkers {
\t\treturn ksErrorf("KS3920: parallel_map max_workers must be between 1 and 64")
\t}
\tfor _, item := range list {
\t\tif !ksParallelScalar(item) || ksContainsCapability(item) {
\t\t\treturn ksErrorf("KS3921: parallel_map input items must be share-safe scalars")
\t\t}
\t}
\tif len(list) == 0 {
\t\treturn []any{}
\t}

\tworkerCount := int(maxWorkers)
\tif workerCount > len(list) {
\t\tworkerCount = len(list)
\t}
\tresults := make([]any, len(list))
\tfailures := make([]*KsError, len(list))
\tvar next int64
\tvar group sync.WaitGroup
\tgroup.Add(workerCount)
\tfor worker := 0; worker < workerCount; worker++ {
\t\tgo func() {
\t\t\tdefer group.Done()
\t\t\tfor {
\t\t\t\tindex := atomic.AddInt64(&next, 1) - 1
\t\t\t\tif index >= int64(len(list)) {
\t\t\t\t\treturn
\t\t\t\t}
\t\t\t\tmapped := function(list[int(index)])
\t\t\t\tif failure, ok := mapped.(*KsError); ok {
\t\t\t\t\tfailures[int(index)] = failure
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\tif !ksParallelScalar(mapped) || ksContainsCapability(mapped) {
\t\t\t\t\tfailures[int(index)] = &KsError{Message: "KS3923: parallel worker returned a non-scalar value"}
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\tresults[int(index)] = mapped
\t\t\t}
\t\t}()
\t}
\tgroup.Wait()
\tfor index := 0; index < len(failures); index++ {
\t\tif failures[index] != nil {
\t\t\treturn failures[index]
\t\t}
\t}
\treturn results
}

'''


def _walk(value: Any):
    if is_dataclass(value):
        yield value
        for field in fields(value):
            yield from _walk(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)


def _is_scalar(type_node: TypeNode) -> bool:
    return isinstance(type_node, NamedType) and type_node.name in _SCALAR_NAMES


def _list_scalar(type_node: TypeNode, location) -> TypeNode:
    if not isinstance(type_node, GenericType) or type_node.name != "List" or len(type_node.arguments) != 1:
        raise _semantic.SemanticError(
            "KS3921", "parallel_map() somut List<scalar> bekler.", location
        )
    item = type_node.arguments[0]
    if not _is_scalar(item):
        raise _semantic.SemanticError(
            "KS3921", "parallel_map() input tipi Bool/Int/Float/String olmalıdır.", location
        )
    return item


def _validate_leaf_worker(checker, worker, item_type: TypeNode, location) -> TypeNode:
    if len(worker.parameters) != 1 or worker.return_type is None:
        raise _semantic.SemanticError(
            "KS3921",
            "parallel_map() worker tam 1 parametre almalı ve scalar değer döndürmelidir.",
            location,
        )
    parameter_type = function_type(worker, worker.parameters[0].type_ref)
    result_type = function_type(worker, worker.return_type)
    if not _is_scalar(parameter_type) or not _is_scalar(result_type):
        raise _semantic.SemanticError(
            "KS3921",
            "parallel_map() worker v1'de yalnız scalar -> scalar olabilir.",
            worker.location,
        )
    if checker.contracts.is_sensitive(parameter_type) or checker.contracts.is_sensitive(result_type):
        raise _semantic.SemanticError(
            "KS2402", "parallel_map() worker capability taşıyamaz.", worker.location
        )
    require_assignable(parameter_type, item_type, "parallel_map() worker girişi", location)

    imports = set(checker.imports)
    for node in _walk(worker.body):
        if not isinstance(node, CallExpression):
            continue
        if isinstance(node.callee, Identifier):
            raise _semantic.SemanticError(
                "KS3922",
                "parallel_map() worker leaf/pure olmalıdır; named/builtin çağrı yapamaz.",
                node.location,
            )
        if isinstance(node.callee, MemberExpression):
            receiver = node.callee.object
            if (
                node.callee.member not in _PURE_MEMBER_CALLS
                or (isinstance(receiver, Identifier) and receiver.name in imports)
            ):
                raise _semantic.SemanticError(
                    "KS3922",
                    "parallel_map() worker yalnız deterministik scalar value-method çağrıları yapabilir.",
                    node.location,
                )
    return result_type


def _typed_infer(checker, expression):
    if not (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name == _BUILTIN
    ):
        return _ORIGINAL_TYPED_INFER(checker, expression)
    if len(expression.arguments) != 3:
        raise _semantic.SemanticError(
            "KS1301",
            f"parallel_map() 3 argüman bekler, {len(expression.arguments)} verildi.",
            expression.location,
        )

    list_type = checker.infer(expression.arguments[0])
    item_type = _list_scalar(list_type, expression.arguments[0].location)

    worker_expression = expression.arguments[1]
    if not isinstance(worker_expression, Identifier):
        raise _semantic.SemanticError(
            "KS3921", "parallel_map() worker doğrudan named function olmalıdır.", worker_expression.location
        )
    worker = checker.functions.get(worker_expression.name)
    if worker is None or worker.name == "main":
        raise _semantic.SemanticError(
            "KS3921", "parallel_map() worker yerel ve main dışı olmalıdır.", worker_expression.location
        )
    checker.infer(worker_expression)
    result_type = _validate_leaf_worker(checker, worker, item_type, expression.location)

    workers_type = checker.infer(expression.arguments[2])
    require_assignable(INT, workers_type, "parallel_map() max_workers", expression.arguments[2].location)
    if isinstance(expression.arguments[2], Literal):
        value = expression.arguments[2].value
        if type(value) is int and not _MIN_WORKERS <= value <= _MAX_WORKERS:
            raise _semantic.SemanticError(
                "KS3920", "parallel_map() max_workers 1..64 aralığında olmalıdır.", expression.arguments[2].location
            )

    return checker.record(expression, union_type(GenericType("List", (result_type,)), ERROR))


def _semantic_expression(self, expression):
    if not (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name == _BUILTIN
    ):
        return _ORIGINAL_SEMANTIC_EXPRESSION(self, expression)
    if len(expression.arguments) != 3:
        raise _semantic.SemanticError(
            "KS1301", f"parallel_map() 3 argüman bekler, {len(expression.arguments)} verildi.", expression.location
        )
    self._check_expression(expression.arguments[0])
    workers = self._check_expression(expression.arguments[2])
    self._require_assignable(("Int",), workers, "parallel_map() max_workers", expression.location)
    return "List or Error"


def _semantic_fallible(self, expression):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, Identifier)
        and expression.callee.name == _BUILTIN
    ):
        return True
    return _ORIGINAL_SEMANTIC_FALLIBLE(self, expression)


def _runtime_evaluate(self, expression):
    if isinstance(expression, Identifier) and expression.name == _BUILTIN:
        return _BUILTIN
    return _ORIGINAL_RUNTIME_EVALUATE(self, expression)


def _runtime_scalar(value: Any) -> bool:
    return type(value) in {bool, int, float, str}


def _runtime_invoke(self, callee, arguments, location):
    if callee != _BUILTIN:
        return _ORIGINAL_RUNTIME_INVOKE(self, callee, arguments, location)
    self._require_arity(_BUILTIN, arguments, 3, location)
    values, worker, max_workers = arguments
    if not isinstance(values, list):
        return _runtime.KsError("KS3921: parallel_map expects List<scalar>")
    if not isinstance(worker, _runtime.FunctionDeclaration):
        return _runtime.KsError("KS3921: parallel_map expects a direct unary worker")
    if type(max_workers) is not int or not _MIN_WORKERS <= max_workers <= _MAX_WORKERS:
        return _runtime.KsError("KS3920: parallel_map max_workers must be between 1 and 64")
    if any(not _runtime_scalar(item) or _runtime._contains_capability(item) for item in values):
        return _runtime.KsError("KS3921: parallel_map input items must be share-safe scalars")

    results: list[Any] = []
    for item in values:
        mapped = self._call_function(worker, [item])
        if isinstance(mapped, _runtime.KsError):
            return mapped
        if not _runtime_scalar(mapped) or _runtime._contains_capability(mapped):
            return _runtime.KsError("KS3923: parallel worker returned a non-scalar value")
        results.append(mapped)
    return results


def _mir_invoke(self, callee, arguments):
    if not (isinstance(callee, _mir._BuiltinRef) and callee.name == _BUILTIN):
        return _ORIGINAL_MIR_INVOKE(self, callee, arguments)
    if len(arguments) != 3:
        raise _mir.MirNativeRuntimeError("parallel_map expects 3 arguments")
    values, worker, max_workers = arguments
    if not isinstance(values, list):
        return _mir._ErrorValue("KS3921: parallel_map expects List<scalar>")
    if type(max_workers) is not int or not _MIN_WORKERS <= max_workers <= _MAX_WORKERS:
        return _mir._ErrorValue("KS3920: parallel_map max_workers must be between 1 and 64")
    if any(not _runtime_scalar(item) or _runtime._contains_capability(item) for item in values):
        return _mir._ErrorValue("KS3921: parallel_map input items must be share-safe scalars")

    results: list[Any] = []
    for item in values:
        mapped = _ORIGINAL_MIR_INVOKE(self, worker, [item])
        if isinstance(mapped, _mir._ErrorValue):
            return mapped
        if not _runtime_scalar(mapped) or _runtime._contains_capability(mapped):
            return _mir._ErrorValue("KS3923: parallel worker returned a non-scalar value")
        results.append(mapped)
    return results


def _codegen_call(self, expression, depth):
    if not (
        isinstance(expression.callee, Identifier)
        and expression.callee.name == _BUILTIN
    ):
        return _ORIGINAL_CODEGEN_CALL(self, expression, depth)
    prelude: list[str] = []
    arguments: list[str] = []
    for argument in expression.arguments:
        value, argument_prelude = self._expression(argument, depth)
        prelude.extend(argument_prelude)
        arguments.append(value)
    self._check_arity(_BUILTIN, arguments, 3, expression.location)
    return f"ksParallelMap({', '.join(arguments)})", prelude


def _patch_go_runtime() -> None:
    prelude = _codegen.RUNTIME_PRELUDE
    anchor = "func ksCallValueMethod(receiver any, method string, arguments ...any) any {"
    if "func ksParallelMap(" not in prelude:
        if anchor not in prelude:
            raise RuntimeError("Go value-method dispatcher changed; parallel_map patch failed closed.")
        prelude = prelude.replace(anchor, _GO_HELPERS.replace("\\t", "\t") + anchor, 1)

    old_depth = '''var ksDepth int

func ksFatal(code string, message string) {
'''
    new_depth = '''var ksDepth int64

func ksFatal(code string, message string) {
'''
    if old_depth in prelude:
        prelude = prelude.replace(old_depth, new_depth, 1)
    elif new_depth not in prelude:
        raise RuntimeError("Go call-depth state changed; parallel runtime patch failed closed.")

    old_enter = '''func ksEnter(location string) {
\tksDepth++
\tif ksDepth > ksMaxDepth {
\t\tksFatal("KS3105", "Çağrı derinliği sınırı aşıldı (512); sonsuz özyineleme olabilir. ["+location+"]")
\t}
}

func ksLeave() {
\tksDepth--
}
'''
    new_enter = '''func ksEnter(location string) {
\tdepth := atomic.AddInt64(&ksDepth, 1)
\tif depth > ksMaxDepth {
\t\tksFatal("KS3105", "Çağrı derinliği sınırı aşıldı (512); sonsuz özyineleme olabilir. ["+location+"]")
\t}
}

func ksLeave() {
\tatomic.AddInt64(&ksDepth, -1)
}
'''
    if old_enter in prelude:
        prelude = prelude.replace(old_enter, new_enter, 1)
    elif new_enter not in prelude:
        raise RuntimeError("Go call-depth guard changed; parallel runtime patch failed closed.")

    _codegen.RUNTIME_PRELUDE = prelude


def _generate_with_atomic_import(self) -> str:
    source = _ORIGINAL_GENERATE(self)
    if '\t"sync/atomic"\n' in source:
        return source
    marker = '\t"sync"\n'
    if marker not in source:
        raise RuntimeError("Go sync import missing; parallel_map import patch failed closed.")
    return source.replace(marker, marker + '\t"sync/atomic"\n', 1)


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    entries = {
        "KS3920": ("Geçersiz paralel worker bütçesi", "Invalid parallel worker budget"),
        "KS3921": ("Parallel map tip sözleşmesi ihlali", "Parallel map type-contract violation"),
        "KS3922": ("Parallel worker saf/leaf değil", "Parallel worker is not pure/leaf"),
        "KS3923": ("Parallel worker runtime tip ihlali", "Parallel worker runtime type violation"),
    }
    for code, (tr, en) in entries.items():
        CATALOG[code] = Diagnostic(
            code,
            tr,
            tr + ".",
            "Scheduler sırasının program sonucuna sızması fail-closed engellendi.",
            "Scalar->scalar, direct leaf worker ve 1..64 worker bütçesi kullanın.",
            "let out = parallel_map(values, square, 4) or return",
        )
        ENGLISH_CATALOG[code] = Diagnostic(
            code,
            en,
            en + ".",
            "Scheduler order was prevented from leaking into program semantics.",
            "Use a direct leaf scalar-to-scalar worker and a 1..64 worker budget.",
            "let out = parallel_map(values, square, 4) or return",
        )


def install_deterministic_parallel_map_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_TYPED_INFER, _ORIGINAL_SEMANTIC_EXPRESSION, _ORIGINAL_SEMANTIC_FALLIBLE
    global _ORIGINAL_RUNTIME_EVALUATE, _ORIGINAL_RUNTIME_INVOKE, _ORIGINAL_MIR_INVOKE
    global _ORIGINAL_CODEGEN_CALL, _ORIGINAL_GENERATE
    if _INSTALLED:
        return

    _semantic.BUILTIN_CALLS.add(_BUILTIN)

    _ORIGINAL_TYPED_INFER = _typed_expr.infer_expression
    _typed_expr.infer_expression = _typed_infer

    _ORIGINAL_SEMANTIC_EXPRESSION = _semantic.SemanticChecker._check_expression
    _semantic.SemanticChecker._check_expression = _semantic_expression
    _ORIGINAL_SEMANTIC_FALLIBLE = _semantic.SemanticChecker._is_fallible_call
    _semantic.SemanticChecker._is_fallible_call = _semantic_fallible

    _ORIGINAL_RUNTIME_EVALUATE = _runtime.Interpreter._evaluate
    _runtime.Interpreter._evaluate = _runtime_evaluate
    _ORIGINAL_RUNTIME_INVOKE = _runtime.Interpreter._invoke
    _runtime.Interpreter._invoke = _runtime_invoke

    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | {_BUILTIN})
    _ORIGINAL_MIR_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _mir_invoke

    _ORIGINAL_CODEGEN_CALL = _codegen.GoCodegen._call
    _codegen.GoCodegen._call = _codegen_call
    _patch_go_runtime()
    _ORIGINAL_GENERATE = _codegen.GoCodegen.generate
    _codegen.GoCodegen.generate = _generate_with_atomic_import

    _register_diagnostics()
    _INSTALLED = True
