"""Static semantics, Typed HIR and MIR CFG support for v0.10."""
from __future__ import annotations

from . import _typed_expr as typed_expr
from . import _typed_ops as typed_ops
from . import ast_nodes as ast
from . import mir_ir
from . import semantic
from . import typed_hir
from .ergonomics_nodes import BreakStatement, ContinueStatement, LetStatement
from .type_contracts import function_type, require_assignable
from .type_system import (
    INT,
    VOID,
    NamedType,
    UnknownType,
    alternatives,
    is_named,
    union_type,
)

_INSTALLED = False


def _element_type_from_annotation(annotation):
    spelling = str(annotation)
    if not spelling.startswith("List<") or not spelling.endswith(">"):
        return None
    return spelling[5:-1].strip() or None


def _iterable_item_type(checker, expression):
    if isinstance(expression, ast.ListLiteral):
        if not expression.items:
            return None
        inferred = [checker._check_expression(item) for item in expression.items]
        first = inferred[0]
        return first if all(item == first for item in inferred) else None
    if isinstance(expression, ast.Identifier):
        return getattr(checker, "_v010_element_types", {}).get(expression.name)
    if isinstance(expression, ast.CallExpression) and isinstance(
        expression.callee, ast.MemberExpression
    ):
        receiver = checker._check_expression(expression.callee.object)
        member = expression.callee.member
        if receiver == "String" and member == "split":
            return "String"
        if receiver == "Map" and member == "keys":
            return "String"
        if receiver == "List" and member in {"push", "sort", "filter"}:
            return _iterable_item_type(checker, expression.callee.object)
    return None


def _coarse_collection(expected, actual):
    if actual not in {"List", "Map"} or len(expected) != 1:
        return False
    item = next(iter(expected))
    return item == actual or item.startswith(actual + "<")


def _attach_type_details(error, expected, actual):
    error.v010_details = {
        "en": f"Expected {expected}, found {actual or 'unknown'}.",
        "tr": f"Beklenen {expected}, bulunan {actual or 'bilinmiyor'}.",
    }
    return error


def _statement(self, statement):
    if isinstance(statement, LetStatement):
        actual = self._check_expression(statement.value)
        declared = actual
        if statement.annotation is not None:
            expected = str(statement.annotation)
            if not _coarse_collection(statement.annotation.names, actual):
                try:
                    self._require_assignable(
                        statement.annotation.names,
                        actual,
                        f"'{statement.name}' yerel tip anotasyonu",
                        statement.location,
                    )
                except semantic.SemanticError as error:
                    if error.code == "KS1301":
                        raise _attach_type_details(error, expected, actual) from error
                    raise
            base = expected.split("<", 1)[0]
            # Legacy semantic method tables understand List and Map by their
            # coarse names. Typed HIR immediately follows and retains the full
            # structural List<T>/Map<String,V> contract.
            declared = base if base in {"List", "Map"} else expected
        self._declare(
            semantic.Symbol(
                statement.name,
                declared,
                statement.is_mutable,
                statement.location,
            )
        )
        element_type = (
            _element_type_from_annotation(statement.annotation)
            if statement.annotation is not None
            else _iterable_item_type(self, statement.value)
        )
        if element_type is not None:
            if not hasattr(self, "_v010_element_types"):
                self._v010_element_types = {}
            self._v010_element_types[statement.name] = element_type
        self.variable_count += 1
        return
    if isinstance(statement, (BreakStatement, ContinueStatement)):
        if getattr(self, "_v010_loop_depth", 0) <= 0:
            word = "break" if isinstance(statement, BreakStatement) else "continue"
            raise semantic.SemanticError(
                "KS1901",
                f"'{word}' bir for veya while döngüsünün içinde değil.",
                statement.location,
            )
        return
    if isinstance(statement, ast.ForStatement):
        iterable_type = self._check_expression(statement.iterable)
        if iterable_type is not None and iterable_type != "List":
            raise semantic.SemanticError(
                "KS1301",
                f"'for ... in' yalnızca List üzerinde çalışır, {iterable_type} bulundu.",
                statement.location,
            )
        item_type = _iterable_item_type(self, statement.iterable)
        self._v010_loop_depth = getattr(self, "_v010_loop_depth", 0) + 1
        self.scopes.append({})
        try:
            self._declare(
                semantic.Symbol(
                    statement.variable,
                    item_type,
                    False,
                    statement.location,
                )
            )
            self.variable_count += 1
            self._check_statements(statement.body)
        finally:
            self.scopes.pop()
            self._v010_loop_depth -= 1
        return
    if isinstance(statement, ast.WhileStatement):
        self._v010_loop_depth = getattr(self, "_v010_loop_depth", 0) + 1
        try:
            return _statement.original(self, statement)
        finally:
            self._v010_loop_depth -= 1
    return _statement.original(self, statement)


def _block_type(self, block):
    self.scopes.append({})
    try:
        if not block.statements:
            return "Void"
        for item in block.statements[:-1]:
            self._check_statement(item)
        tail = block.statements[-1]
        if isinstance(tail, ast.ExpressionStatement):
            return self._check_expression(tail.expression)
        self._check_statement(tail)
        return "Void"
    finally:
        self.scopes.pop()


def _match(self, expression):
    value_type = self._check_expression(expression.value)
    variants = self._enum_shape(value_type)
    if variants is None:
        raise semantic.SemanticError(
            "KS1702",
            f"match bir enum, Option veya Result bekler; {value_type or '<bilinmiyor>'} bulundu.",
            expression.location,
        )
    seen = set()
    result = None
    for arm in expression.arms:
        if arm.variant in seen:
            raise semantic.SemanticError(
                "KS1702",
                f"match içinde '{arm.variant}' kolu birden fazla yazılmış.",
                arm.location,
            )
        seen.add(arm.variant)
        if arm.variant not in variants:
            raise semantic.SemanticError(
                "KS1702",
                f"'{arm.variant}' varyantı {value_type} tipine ait değil.",
                arm.location,
            )
        payload = variants[arm.variant]
        if payload is None and arm.binding is not None:
            raise semantic.SemanticError(
                "KS1702",
                f"'{arm.variant}' payload taşımadığı için bağlama alamaz.",
                arm.location,
            )
        if payload is not None and arm.binding is None:
            raise semantic.SemanticError(
                "KS1702",
                f"'{arm.variant}' payload taşıdığı için bağlama adı gerektirir.",
                arm.location,
            )
        self.scopes.append({})
        try:
            if arm.binding is not None:
                self._declare(
                    semantic.Symbol(arm.binding, payload, False, arm.location)
                )
            arm_type = (
                _block_type(self, arm.body)
                if isinstance(arm.body, ast.Block)
                else self._check_expression(arm.body)
            )
        finally:
            self.scopes.pop()
        result = self._unify_types(result, arm_type, arm.location)
    missing = set(variants) - seen
    if missing:
        raise semantic.SemanticError(
            "KS1702",
            "match exhaustive olmalıdır; eksik varyantlar: "
            + ", ".join(sorted(missing))
            + ".",
            expression.location,
        )
    return result


def _expression(self, expression):
    if isinstance(expression, ast.AssignmentExpression) and isinstance(
        expression.target, ast.MemberExpression
    ):
        target = expression.target
        if not isinstance(target.object, ast.Identifier):
            raise semantic.SemanticError(
                "KS3201",
                "İç içe struct alan ataması v0.10 kapsamında değildir.",
                expression.location,
            )
        symbol = self._resolve(target.object.name)
        if symbol is None:
            self._raise_unknown_identifier(target.object)
        if not symbol.is_mutable:
            raise semantic.SemanticError(
                "KS3201",
                f"'{target.object.name}' immutable bir struct değeridir; 'let mut' kullanın.",
                expression.location,
            )
        owner_type = self._check_expression(target.object)
        declaration = self.structs.get(owner_type or "")
        if declaration is None:
            raise semantic.SemanticError(
                "KS3201",
                "Alan atamasının hedefi bir struct olmalıdır.",
                expression.location,
            )
        field = next(
            (item for item in declaration.fields if item.name == target.member),
            None,
        )
        if field is None:
            raise semantic.SemanticError(
                "KS1502",
                f"'{owner_type}' struct'ında '{target.member}' alanı yok.",
                target.location,
            )
        actual = self._check_expression(expression.value)
        self._require_assignable(
            field.type_ref.names,
            actual,
            f"'{owner_type}.{field.name}' alan ataması",
            expression.location,
        )
        return str(field.type_ref)
    return _expression.original(self, expression)


def _binary(self, expression):
    if expression.operator != "%":
        return _binary.original(self, expression)
    left = self._check_expression(expression.left)
    right = self._check_expression(expression.right)
    for side, value in (("sol", left), ("sağ", right)):
        if value not in {None, "_", "Int"}:
            raise semantic.SemanticError(
                "KS1301",
                f"'%' işlecinin {side} tarafı Int olmalıdır, {value} bulundu.",
                expression.location,
            )
    return "Int"


def _typed_statement(self, statement):
    if isinstance(statement, LetStatement):
        actual = self.infer(statement.value)
        declared = actual
        if statement.annotation is not None:
            declared = function_type(self.current_function, statement.annotation)
            try:
                require_assignable(
                    declared,
                    actual,
                    f"'{statement.name}' yerel tip anotasyonu",
                    statement.location,
                )
            except semantic.SemanticError as error:
                if error.code == "KS1301":
                    raise _attach_type_details(error, declared, actual) from error
                raise
        self.declare(statement.name, declared, statement.location, "local")
        return
    if isinstance(statement, (BreakStatement, ContinueStatement)):
        return
    return _typed_statement.original(self, statement)


def _typed_block(checker, block):
    checker.scopes.append({})
    try:
        if not block.statements:
            return VOID
        for item in block.statements[:-1]:
            checker.check_statement(item)
        tail = block.statements[-1]
        if isinstance(tail, ast.ExpressionStatement):
            return checker.infer(tail.expression)
        checker.check_statement(tail)
        return VOID
    finally:
        checker.scopes.pop()


def _typed_infer(checker, expression):
    # Block-arm Match used to be typed here before core Typed-HIR owned block
    # result semantics. Keeping that compatibility path would bypass
    # record_match_resolution() and strip the compiler-owned Owner::Variant
    # identity required by sealed MIR. Match now always delegates to the
    # canonical Typed-HIR implementation.
    return _typed_infer.original(checker, expression)


def _typed_binary(left, operator, right, location):
    if operator != "%":
        return _typed_binary.original(left, operator, right, location)
    for item in (*alternatives(left), *alternatives(right)):
        if isinstance(item, UnknownType):
            continue
        if not is_named(item, "Int"):
            raise semantic.SemanticError(
                "KS1301",
                "'%' işleci yalnızca Int % Int için tanımlıdır.",
                location,
            )
    return INT


def _mir_init(self, declaration, report):
    _mir_init.original(self, declaration, report)
    self._v010_loops = []


def _mir_while(self, statement):
    condition, body, exit_ = self._new_block(), self._new_block(), self._new_block()
    self._terminate(mir_ir.MirJump(condition))
    self.current = condition
    value = self._lower_expression(statement.condition)
    self._terminate(mir_ir.MirBranch(value, body, exit_))
    self.current = body
    self._v010_loops.append((condition, exit_))
    try:
        self._lower_block(statement.body)
    finally:
        self._v010_loops.pop()
    if self.blocks[self.current].terminator is None:
        self._terminate(mir_ir.MirJump(condition))
    self.current = exit_


def _mir_for(self, statement):
    self._lower_expression(statement.iterable)
    condition, body, exit_ = self._new_block(), self._new_block(), self._new_block()
    self._terminate(mir_ir.MirJump(condition))
    self.current = condition
    value = self._new_value()
    self._emit(
        mir_ir.MirAstFallback(
            value,
            "ForHasNext",
            NamedType("Bool"),
            statement.location,
        )
    )
    self._terminate(mir_ir.MirBranch(value, body, exit_))
    self.current = body
    self._emit(
        mir_ir.MirAstFallback(None, "ForBind", UnknownType(), statement.location)
    )
    self._v010_loops.append((condition, exit_))
    try:
        self._lower_block(statement.body)
    finally:
        self._v010_loops.pop()
    if self.blocks[self.current].terminator is None:
        self._terminate(mir_ir.MirJump(condition))
    self.current = exit_


def _mir_statement(self, statement):
    if isinstance(statement, BreakStatement):
        if self._v010_loops:
            self._terminate(mir_ir.MirJump(self._v010_loops[-1][1]))
        else:
            self._emit(
                mir_ir.MirAstFallback(
                    None,
                    "BreakOutsideLoop",
                    UnknownType(),
                    statement.location,
                )
            )
        return
    if isinstance(statement, ContinueStatement):
        if self._v010_loops:
            self._terminate(mir_ir.MirJump(self._v010_loops[-1][0]))
        else:
            self._emit(
                mir_ir.MirAstFallback(
                    None,
                    "ContinueOutsideLoop",
                    UnknownType(),
                    statement.location,
                )
            )
        return
    if isinstance(statement, ast.ForStatement):
        return _mir_for(self, statement)
    return _mir_statement.original(self, statement)


def install_semantics_v010() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    semantic.ARITHMETIC_OPERATORS.add("%")
    _statement.original = semantic.SemanticChecker._check_statement
    semantic.SemanticChecker._check_statement = _statement
    _expression.original = semantic.SemanticChecker._check_expression
    semantic.SemanticChecker._check_expression = _expression
    semantic.SemanticChecker._check_match_expression = _match
    _binary.original = semantic.SemanticChecker._check_binary
    semantic.SemanticChecker._check_binary = _binary
    _typed_statement.original = typed_hir.TypedHIRChecker.check_statement
    typed_hir.TypedHIRChecker.check_statement = _typed_statement
    _typed_infer.original = typed_expr.infer_expression
    typed_expr.infer_expression = _typed_infer
    _typed_binary.original = typed_ops.binary_type
    typed_ops.binary_type = _typed_binary
    typed_expr.binary_type = _typed_binary
    _mir_init.original = mir_ir._FunctionLowerer.__init__
    mir_ir._FunctionLowerer.__init__ = _mir_init
    _mir_statement.original = mir_ir._FunctionLowerer._lower_statement
    mir_ir._FunctionLowerer._lower_statement = _mir_statement
    mir_ir._FunctionLowerer._lower_while = _mir_while
    _INSTALLED = True
