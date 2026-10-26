"""Affine ownership for authority-bearing Koschei values.

V1 makes capability-bearing values move-only without making ordinary authority
operations single-use. Method receivers are borrowed; ownership transfer sites
(`let` aliases, function arguments, returns, aggregate fields) move the value.
After a move the old binding cannot be referenced again.

This pass runs after Typed HIR so ownership follows structural types rather than
legacy string heuristics. It is intentionally conservative around control flow:
a move in either branch makes the outer binding unavailable after the branch,
and moving an outer affine binding from a repeating loop is rejected until a
future path-sensitive borrow checker can prove single execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    AssignmentExpression,
    BinaryExpression,
    Block,
    BreakStatement,
    CallExpression,
    ContinueStatement,
    Expression,
    ExpressionStatement,
    ForStatement,
    Identifier,
    IfStatement,
    InterpolatedString,
    LetStatement,
    ListLiteral,
    Literal,
    MapLiteral,
    MatchExpression,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Program,
    ReturnStatement,
    SourceLocation,
    StructLiteral,
    UnaryExpression,
    WhileStatement,
)
from .semantic import ImportedModule, SemanticError
from .type_contracts import TypeContractValidator, function_type
from .type_system import NamedType, TypeNode, UnknownType, render_type
from .typed_hir import TypedHIRReport


_MOVE = "move"
_BORROW = "borrow"


@dataclass(frozen=True, slots=True)
class _Binding:
    id: int
    name: str
    type: TypeNode
    location: SourceLocation


class AffineResourceChecker:
    def __init__(
        self,
        program: Program,
        imports: dict[str, ImportedModule],
        typed_report: TypedHIRReport,
    ) -> None:
        self.program = program
        self.imports = imports
        self.contracts = TypeContractValidator(program, imports)
        self.expression_types = {
            id(item.expression): item.type for item in typed_report.expressions
        }
        self.scopes: list[dict[str, _Binding]] = []
        self.moved: set[int] = set()
        self.move_locations: dict[int, SourceLocation] = {}
        self._next_binding_id = 1

    def check(self) -> None:
        for function in self.program.declarations:
            self.scopes.append({})
            try:
                for parameter in function.parameters:
                    self._declare(
                        parameter.name,
                        function_type(function, parameter.type_ref),
                        parameter.location,
                        mutable=False,
                    )
                self._check_block(function.body, nested=False)
            finally:
                self.scopes.pop()
                self.moved.clear()
                self.move_locations.clear()

    def _type_of(self, expression: Expression) -> TypeNode:
        return self.expression_types.get(id(expression), UnknownType())

    def _is_affine(self, type_node: TypeNode) -> bool:
        return self.contracts.is_sensitive(type_node)

    def _declare(
        self,
        name: str,
        type_node: TypeNode,
        location: SourceLocation,
        *,
        mutable: bool,
    ) -> _Binding:
        if mutable and self._is_affine(type_node):
            raise SemanticError(
                "KS3930",
                f"'{name}' affine bir resource ({render_type(type_node)}); "
                "'let mut' ile alias/reassignment yüzeyi açılamaz.",
                location,
            )
        binding = _Binding(
            id=self._next_binding_id,
            name=name,
            type=type_node,
            location=location,
        )
        self._next_binding_id += 1
        self.scopes[-1][name] = binding
        return binding

    def _resolve(self, name: str) -> _Binding | None:
        for scope in reversed(self.scopes):
            binding = scope.get(name)
            if binding is not None:
                return binding
        return None

    def _outer_binding_ids(self) -> set[int]:
        return {binding.id for scope in self.scopes for binding in scope.values()}

    def _mark_move(self, binding: _Binding, location: SourceLocation) -> None:
        if binding.id in self.moved:
            first = self.move_locations.get(binding.id, binding.location)
            raise SemanticError(
                "KS3931",
                f"'{binding.name}' affine resource'u daha önce move edildi "
                f"(ilk move: satır {first.line}, sütun {first.column}); "
                "eski binding tekrar kullanılamaz.",
                location,
            )
        self.moved.add(binding.id)
        self.move_locations[binding.id] = location

    def _use_identifier(self, expression: Identifier, context: str) -> None:
        binding = self._resolve(expression.name)
        if binding is None or not self._is_affine(binding.type):
            return
        if binding.id in self.moved:
            first = self.move_locations.get(binding.id, binding.location)
            raise SemanticError(
                "KS3931",
                f"'{binding.name}' affine resource'u move sonrası kullanılıyor "
                f"(ilk move: satır {first.line}, sütun {first.column}).",
                expression.location,
            )
        if context == _MOVE:
            self._mark_move(binding, expression.location)

    def _root_identifier(self, expression: Expression) -> Identifier | None:
        current = expression
        while isinstance(current, MemberExpression):
            current = current.object
        return current if isinstance(current, Identifier) else None

    def _check_block(self, block: Block, *, nested: bool = True) -> None:
        if nested:
            self.scopes.append({})
        try:
            for statement in block.statements:
                self._check_statement(statement)
        finally:
            if nested:
                local_ids = {binding.id for binding in self.scopes[-1].values()}
                self.moved.difference_update(local_ids)
                for binding_id in local_ids:
                    self.move_locations.pop(binding_id, None)
                self.scopes.pop()

    def _check_statement(self, statement) -> None:
        if isinstance(statement, LetStatement):
            value_type = self._type_of(statement.value)
            self._check_expression(
                statement.value,
                _MOVE if self._is_affine(value_type) else _BORROW,
            )
            self._declare(
                statement.name,
                value_type,
                statement.location,
                mutable=statement.is_mutable,
            )
            return

        if isinstance(statement, ReturnStatement):
            if statement.value is not None:
                value_type = self._type_of(statement.value)
                self._check_expression(
                    statement.value,
                    _MOVE if self._is_affine(value_type) else _BORROW,
                )
            return

        if isinstance(statement, ExpressionStatement):
            # A bare affine expression is only observed/discarded here. Calls
            # still move affine arguments through their own argument contexts.
            self._check_expression(statement.expression, _BORROW)
            return

        if isinstance(statement, IfStatement):
            self._check_expression(statement.condition, _BORROW)
            self._check_if(statement)
            return

        if isinstance(statement, WhileStatement):
            self._check_expression(statement.condition, _BORROW)
            self._check_repeating_block(statement.body, statement.location)
            return

        if isinstance(statement, ForStatement):
            self._check_expression(statement.iterable, _BORROW)
            outer_ids = self._outer_binding_ids()
            before = set(self.moved)
            before_locations = dict(self.move_locations)
            self.scopes.append({})
            try:
                item_type = UnknownType()
                iterable_type = self._type_of(statement.iterable)
                arguments = getattr(iterable_type, "arguments", ())
                if arguments:
                    item_type = arguments[0]
                self._declare(
                    statement.variable,
                    item_type,
                    statement.location,
                    mutable=False,
                )
                self._check_block(statement.body, nested=False)
                newly_moved = (self.moved - before) & outer_ids
                if newly_moved:
                    binding_id = min(newly_moved)
                    binding = self._binding_by_id(binding_id)
                    location = self.move_locations.get(binding_id, statement.location)
                    raise SemanticError(
                        "KS3932",
                        f"'{binding.name}' outer-scope affine resource'u repeating "
                        "for gövdesi içinde move edilemez; ikinci iterasyon double-move "
                        "üretebilir.",
                        location,
                    )
            finally:
                self.scopes.pop()
                self.moved = before
                self.move_locations = before_locations
            return

        if isinstance(statement, (BreakStatement, ContinueStatement)):
            return

        raise AssertionError(type(statement).__name__)

    def _binding_by_id(self, binding_id: int) -> _Binding:
        for scope in self.scopes:
            for binding in scope.values():
                if binding.id == binding_id:
                    return binding
        raise AssertionError(f"unknown affine binding id {binding_id}")

    def _check_if(self, statement: IfStatement) -> None:
        outer_ids = self._outer_binding_ids()
        before = set(self.moved)
        before_locations = dict(self.move_locations)

        self._check_block(statement.then_block)
        then_moved = self.moved & outer_ids
        then_locations = {
            binding_id: self.move_locations[binding_id]
            for binding_id in then_moved
            if binding_id in self.move_locations
        }

        self.moved = set(before)
        self.move_locations = dict(before_locations)
        if isinstance(statement.else_branch, Block):
            self._check_block(statement.else_branch)
        elif isinstance(statement.else_branch, IfStatement):
            self._check_expression(statement.else_branch.condition, _BORROW)
            self._check_if(statement.else_branch)
        else_moved = self.moved & outer_ids
        else_locations = {
            binding_id: self.move_locations[binding_id]
            for binding_id in else_moved
            if binding_id in self.move_locations
        }

        joined = before | then_moved | else_moved
        locations = dict(before_locations)
        for binding_id in sorted(then_locations):
            locations.setdefault(binding_id, then_locations[binding_id])
        for binding_id in sorted(else_locations):
            locations.setdefault(binding_id, else_locations[binding_id])
        self.moved = joined
        self.move_locations = locations

    def _check_repeating_block(self, block: Block, location: SourceLocation) -> None:
        outer_ids = self._outer_binding_ids()
        before = set(self.moved)
        before_locations = dict(self.move_locations)
        try:
            self._check_block(block)
            newly_moved = (self.moved - before) & outer_ids
            if newly_moved:
                binding_id = min(newly_moved)
                binding = self._binding_by_id(binding_id)
                move_location = self.move_locations.get(binding_id, location)
                raise SemanticError(
                    "KS3932",
                    f"'{binding.name}' outer-scope affine resource'u repeating "
                    "loop içinde move edilemez; iterasyon sayısı ownership için "
                    "statik olarak güvenli değil.",
                    move_location,
                )
        finally:
            self.moved = before
            self.move_locations = before_locations

    def _check_expression(self, expression: Expression, context: str) -> None:
        if isinstance(expression, Literal):
            return

        if isinstance(expression, Identifier):
            self._use_identifier(expression, context)
            return

        if isinstance(expression, InterpolatedString):
            for part in expression.parts:
                self._check_expression(part, _BORROW)
            return

        if isinstance(expression, ListLiteral):
            for item in expression.items:
                item_type = self._type_of(item)
                self._check_expression(
                    item,
                    _MOVE if self._is_affine(item_type) else _BORROW,
                )
            return

        if isinstance(expression, MapLiteral):
            for key, value in expression.entries:
                self._check_expression(key, _BORROW)
                value_type = self._type_of(value)
                self._check_expression(
                    value,
                    _MOVE if self._is_affine(value_type) else _BORROW,
                )
            return

        if isinstance(expression, StructLiteral):
            for _, value in expression.fields:
                value_type = self._type_of(value)
                self._check_expression(
                    value,
                    _MOVE if self._is_affine(value_type) else _BORROW,
                )
            return

        if isinstance(expression, MemberExpression):
            # Reading a field/method receiver is a borrow by default. Moving an
            # affine field conservatively moves the entire owner binding. The
            # SystemCaps projection is special: caps.net/caps.disk derive a root
            # authority token without consuming the whole SystemCaps handle.
            self._check_expression(expression.object, _BORROW)
            result_type = self._type_of(expression)
            if context == _MOVE and self._is_affine(result_type):
                object_type = self._type_of(expression.object)
                if not (
                    isinstance(object_type, NamedType)
                    and object_type.name == "SystemCaps"
                ):
                    root = self._root_identifier(expression.object)
                    if root is not None:
                        binding = self._resolve(root.name)
                        if binding is not None and self._is_affine(binding.type):
                            self._mark_move(binding, expression.location)
            return

        if isinstance(expression, CallExpression):
            if isinstance(expression.callee, MemberExpression):
                # Method receivers are borrowed. This is what allows a single
                # owned capability token to authorize multiple legitimate ops.
                self._check_expression(expression.callee.object, _BORROW)
            else:
                self._check_expression(expression.callee, _BORROW)
            for argument in expression.arguments:
                argument_type = self._type_of(argument)
                self._check_expression(
                    argument,
                    _MOVE if self._is_affine(argument_type) else _BORROW,
                )
            return

        if isinstance(expression, BinaryExpression):
            self._check_expression(expression.left, _BORROW)
            self._check_expression(expression.right, _BORROW)
            return

        if isinstance(expression, UnaryExpression):
            self._check_expression(expression.operand, _BORROW)
            return

        if isinstance(expression, OrReturnExpression):
            value_type = self._type_of(expression.value)
            self._check_expression(
                expression.value,
                context if self._is_affine(value_type) else _BORROW,
            )
            if expression.error is not None:
                error_type = self._type_of(expression.error)
                self._check_expression(
                    expression.error,
                    _MOVE if self._is_affine(error_type) else _BORROW,
                )
            return

        if isinstance(expression, OrElseExpression):
            value_type = self._type_of(expression.value)
            fallback_type = self._type_of(expression.fallback)
            self._check_expression(
                expression.value,
                context if self._is_affine(value_type) else _BORROW,
            )
            self._check_expression(
                expression.fallback,
                context if self._is_affine(fallback_type) else _BORROW,
            )
            return

        if isinstance(expression, OrBlockExpression):
            value_type = self._type_of(expression.value)
            self._check_expression(
                expression.value,
                context if self._is_affine(value_type) else _BORROW,
            )
            self._check_block(expression.handler)
            return

        if isinstance(expression, MatchExpression):
            self._check_expression(expression.value, _BORROW)
            outer_ids = self._outer_binding_ids()
            before = set(self.moved)
            before_locations = dict(self.move_locations)
            joined = set(before)
            joined_locations = dict(before_locations)
            for arm in expression.arms:
                self.moved = set(before)
                self.move_locations = dict(before_locations)
                self.scopes.append({})
                try:
                    if arm.binding is not None:
                        self._declare(
                            arm.binding,
                            UnknownType(),
                            arm.location,
                            mutable=False,
                        )
                    if isinstance(arm.body, Block):
                        self._check_block(arm.body, nested=False)
                    else:
                        arm_type = self._type_of(arm.body)
                        self._check_expression(
                            arm.body,
                            context if self._is_affine(arm_type) else _BORROW,
                        )
                    arm_moved = self.moved & outer_ids
                    joined.update(arm_moved)
                    for binding_id in arm_moved:
                        if binding_id in self.move_locations:
                            joined_locations.setdefault(
                                binding_id, self.move_locations[binding_id]
                            )
                finally:
                    self.scopes.pop()
            self.moved = joined
            self.move_locations = joined_locations
            return

        if isinstance(expression, AssignmentExpression):
            value_type = self._type_of(expression.value)
            self._check_expression(
                expression.value,
                _MOVE if self._is_affine(value_type) else _BORROW,
            )
            self._check_expression(expression.target, _BORROW)
            return

        raise AssertionError(type(expression).__name__)


def check_affine_resources(
    program: Program,
    imports: dict[str, ImportedModule],
    typed_report: TypedHIRReport,
) -> None:
    AffineResourceChecker(program, imports, typed_report).check()


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    CATALOG.setdefault(
        "KS3930",
        Diagnostic(
            "KS3930",
            "Affine resource mutable olamaz",
            "Capability veya capability taşıyan resource 'let mut' ile tanımlandı.",
            "Mutable ownership alias/reassignment yüzeyi authority takibini belirsizleştirir.",
            "Resource'u immutable tutun; sahipliği açık move ile başka binding'e aktarın.",
            "let next = authority",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3930",
        Diagnostic(
            "KS3930",
            "Affine resource cannot be mutable",
            "A capability-bearing resource was declared with 'let mut'.",
            "Mutable ownership would make authority alias/reassignment tracking ambiguous.",
            "Keep the resource immutable and transfer ownership with an explicit value move.",
            "let next = authority",
        ),
    )
    CATALOG.setdefault(
        "KS3931",
        Diagnostic(
            "KS3931",
            "Affine resource move sonrası kullanıldı",
            "Bir authority-bearing binding sahipliği aktarıldıktan sonra tekrar referanslandı.",
            "Aynı authority tokenının iki canlı alias'a dönüşmesi engellendi.",
            "Eski binding'i bırakın ve move sonucundaki yeni owner'ı kullanın.",
            "let next = authority\nuse(next)",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3931",
        Diagnostic(
            "KS3931",
            "Affine resource used after move",
            "An authority-bearing binding was referenced after ownership transfer.",
            "Koschei prevented one authority token from becoming two live aliases.",
            "Stop using the old binding and continue through the new owner.",
            "let next = authority\nuse(next)",
        ),
    )
    CATALOG.setdefault(
        "KS3932",
        Diagnostic(
            "KS3932",
            "Loop içinde güvenli olmayan affine move",
            "Outer-scope affine resource tekrar eden bir loop gövdesinde move edildi.",
            "İkinci iterasyon aynı resource'u tekrar consume edebilir.",
            "Ownership transferini loop dışına taşıyın veya her iterasyonda yeni resource üretin.",
            "let owned = handoff(authority)",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3932",
        Diagnostic(
            "KS3932",
            "Unsafe affine move inside loop",
            "An outer-scope affine resource was moved from a repeating loop body.",
            "A later iteration could consume the same resource twice.",
            "Move ownership outside the loop or create a fresh resource per iteration.",
            "let owned = handoff(authority)",
        ),
    )


_register_diagnostics()
