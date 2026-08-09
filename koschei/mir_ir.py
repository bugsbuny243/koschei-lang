"""Normalized MIR nodes and control-flow lowering for Koschei V5.

The lowering is intentionally incremental. Core scalar expressions and structured
`if`/`while` statements become explicit instructions and basic blocks. Lexical
local bindings are resolved to stable function-unique MIR names during lowering,
so backends do not need to rediscover source-language scope. Language constructs
that still need semantic design are represented by an explicit `MirAstFallback`
node instead of being silently erased or misrepresented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

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
    FunctionDeclaration,
    Identifier,
    IfStatement,
    LetStatement,
    Literal,
    MemberExpression,
    ReturnStatement,
    SourceLocation,
    Statement,
    UnaryExpression,
    WhileStatement,
)
from .type_system import TypeNode, UnknownType, render_type


@dataclass(frozen=True, slots=True)
class MirConst:
    target: int
    value: object
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirLoad:
    target: int
    name: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirBind:
    name: str
    source: int
    is_mutable: bool
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirStore:
    name: str
    source: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirUnary:
    target: int
    operator: str
    operand: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirBinary:
    target: int
    operator: str
    left: int
    right: int
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirMember:
    target: int
    object: int
    member: str
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirCall:
    target: int
    callee: int
    arguments: tuple[int, ...]
    type: TypeNode
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class MirAstFallback:
    """An explicit migration boundary for a construct not normalized yet."""

    target: int | None
    node_kind: str
    type: TypeNode
    location: SourceLocation


MirInstruction: TypeAlias = (
    MirConst
    | MirLoad
    | MirBind
    | MirStore
    | MirUnary
    | MirBinary
    | MirMember
    | MirCall
    | MirAstFallback
)


@dataclass(frozen=True, slots=True)
class MirReturn:
    value: int | None


@dataclass(frozen=True, slots=True)
class MirJump:
    target: int


@dataclass(frozen=True, slots=True)
class MirBranch:
    condition: int
    then_block: int
    else_block: int


@dataclass(frozen=True, slots=True)
class MirUnreachable:
    reason: str


MirTerminator: TypeAlias = MirReturn | MirJump | MirBranch | MirUnreachable


@dataclass(frozen=True, slots=True)
class MirBasicBlock:
    id: int
    instructions: tuple[MirInstruction, ...]
    terminator: MirTerminator


@dataclass(slots=True)
class _MutableBlock:
    id: int
    instructions: list[MirInstruction]
    terminator: MirTerminator | None = None


class _FunctionLowerer:
    def __init__(self, declaration: FunctionDeclaration, typed_report) -> None:
        self.declaration = declaration
        self.typed_report = typed_report
        self.blocks: dict[int, _MutableBlock] = {0: _MutableBlock(0, [])}
        self.current = 0
        self.next_block = 1
        self.next_value = 0
        self.next_binding = 0
        self.loop_targets: list[tuple[int, int]] = []
        parameter_scope = {
            parameter.name: parameter.name for parameter in declaration.parameters
        }
        self.scopes: list[dict[str, str]] = [parameter_scope]
        self.used_binding_names: set[str] = set(parameter_scope.values())

    def lower(self) -> tuple[MirBasicBlock, ...]:
        self._lower_block(self.declaration.body, scoped=False)
        current = self.blocks[self.current]
        if current.terminator is None:
            current.terminator = MirReturn(None)
        frozen = tuple(
            MirBasicBlock(
                block.id,
                tuple(block.instructions),
                block.terminator
                if block.terminator is not None
                else MirUnreachable("unterminated lowering block"),
            )
            for block in sorted(self.blocks.values(), key=lambda item: item.id)
        )
        validate_blocks(frozen)
        return frozen

    def _type_of(self, expression: Expression) -> TypeNode:
        for item in self.typed_report.expressions:
            if item.expression is expression:
                return item.type
        return UnknownType()

    def _new_value(self) -> int:
        value = self.next_value
        self.next_value += 1
        return value

    def _new_block(self) -> int:
        block = self.next_block
        self.next_block += 1
        self.blocks[block] = _MutableBlock(block, [])
        return block

    def _new_binding_name(self, source_name: str) -> str:
        if source_name not in self.used_binding_names:
            internal = source_name
        else:
            while True:
                internal = f"{source_name}$mir{self.next_binding}"
                self.next_binding += 1
                if internal not in self.used_binding_names:
                    break
        self.used_binding_names.add(internal)
        self.scopes[-1][source_name] = internal
        return internal

    def _resolve_binding_name(self, source_name: str) -> str | None:
        for scope in reversed(self.scopes):
            resolved = scope.get(source_name)
            if resolved is not None:
                return resolved
        return None

    def _emit(self, instruction: MirInstruction) -> None:
        block = self.blocks[self.current]
        if block.terminator is not None:
            raise ValueError(f"cannot emit into terminated MIR block {block.id}")
        block.instructions.append(instruction)

    def _terminate(self, terminator: MirTerminator) -> None:
        block = self.blocks[self.current]
        if block.terminator is not None:
            raise ValueError(f"MIR block {block.id} already has a terminator")
        block.terminator = terminator

    def _lower_block(self, block: Block, *, scoped: bool = True) -> None:
        if scoped:
            self.scopes.append({})
        try:
            for statement in block.statements:
                if self.blocks[self.current].terminator is not None:
                    break
                self._lower_statement(statement)
        finally:
            if scoped:
                self.scopes.pop()

    def _lower_statement(self, statement: Statement) -> None:
        if isinstance(statement, LetStatement):
            value = self._lower_expression(statement.value)
            binding_name = self._new_binding_name(statement.name)
            self._emit(
                MirBind(
                    binding_name,
                    value,
                    statement.is_mutable,
                    self._type_of(statement.value),
                    statement.location,
                )
            )
            return
        if isinstance(statement, ExpressionStatement):
            self._lower_expression(statement.expression)
            return
        if isinstance(statement, ReturnStatement):
            value = (
                self._lower_expression(statement.value)
                if statement.value is not None
                else None
            )
            self._terminate(MirReturn(value))
            return
        if isinstance(statement, IfStatement):
            self._lower_if(statement)
            return
        if isinstance(statement, WhileStatement):
            self._lower_while(statement)
            return
        if isinstance(statement, BreakStatement):
            if not self.loop_targets:
                raise ValueError("break cannot be lowered outside a loop")
            break_target, _ = self.loop_targets[-1]
            self._terminate(MirJump(break_target))
            return
        if isinstance(statement, ContinueStatement):
            if not self.loop_targets:
                raise ValueError("continue cannot be lowered outside a loop")
            _, continue_target = self.loop_targets[-1]
            self._terminate(MirJump(continue_target))
            return
        if isinstance(statement, ForStatement):
            self._emit(
                MirAstFallback(
                    None,
                    type(statement).__name__,
                    UnknownType(),
                    statement.location,
                )
            )
            return
        self._emit(
            MirAstFallback(
                None,
                type(statement).__name__,
                UnknownType(),
                statement.location,
            )
        )

    def _lower_if(self, statement: IfStatement) -> None:
        condition = self._lower_expression(statement.condition)
        then_block = self._new_block()
        else_block = self._new_block()
        join_block = self._new_block()
        self._terminate(MirBranch(condition, then_block, else_block))

        self.current = then_block
        self._lower_block(statement.then_block)
        if self.blocks[self.current].terminator is None:
            self._terminate(MirJump(join_block))

        self.current = else_block
        if isinstance(statement.else_branch, Block):
            self._lower_block(statement.else_branch)
        elif isinstance(statement.else_branch, IfStatement):
            self._lower_if(statement.else_branch)
        if self.blocks[self.current].terminator is None:
            self._terminate(MirJump(join_block))

        self.current = join_block

    def _lower_while(self, statement: WhileStatement) -> None:
        condition_block = self._new_block()
        body_block = self._new_block()
        exit_block = self._new_block()
        self._terminate(MirJump(condition_block))

        self.current = condition_block
        condition = self._lower_expression(statement.condition)
        self._terminate(MirBranch(condition, body_block, exit_block))

        self.current = body_block
        self.loop_targets.append((exit_block, condition_block))
        try:
            self._lower_block(statement.body)
        finally:
            self.loop_targets.pop()
        if self.blocks[self.current].terminator is None:
            self._terminate(MirJump(condition_block))

        self.current = exit_block

    def _lower_expression(self, expression: Expression) -> int:
        result_type = self._type_of(expression)
        if isinstance(expression, Literal):
            target = self._new_value()
            self._emit(MirConst(target, expression.value, result_type, expression.location))
            return target
        if isinstance(expression, Identifier):
            target = self._new_value()
            name = self._resolve_binding_name(expression.name) or expression.name
            self._emit(MirLoad(target, name, result_type, expression.location))
            return target
        if isinstance(expression, UnaryExpression):
            operand = self._lower_expression(expression.operand)
            target = self._new_value()
            self._emit(
                MirUnary(
                    target,
                    expression.operator,
                    operand,
                    result_type,
                    expression.location,
                )
            )
            return target
        if isinstance(expression, BinaryExpression):
            left = self._lower_expression(expression.left)
            right = self._lower_expression(expression.right)
            target = self._new_value()
            self._emit(
                MirBinary(
                    target,
                    expression.operator,
                    left,
                    right,
                    result_type,
                    expression.location,
                )
            )
            return target
        if isinstance(expression, MemberExpression):
            object_value = self._lower_expression(expression.object)
            target = self._new_value()
            self._emit(
                MirMember(
                    target,
                    object_value,
                    expression.member,
                    result_type,
                    expression.location,
                )
            )
            return target
        if isinstance(expression, CallExpression):
            callee = self._lower_expression(expression.callee)
            arguments = tuple(
                self._lower_expression(argument) for argument in expression.arguments
            )
            target = self._new_value()
            self._emit(
                MirCall(target, callee, arguments, result_type, expression.location)
            )
            return target
        if isinstance(expression, AssignmentExpression):
            value = self._lower_expression(expression.value)
            if isinstance(expression.target, Identifier):
                name = self._resolve_binding_name(expression.target.name)
                if name is None:
                    name = expression.target.name
                self._emit(
                    MirStore(
                        name,
                        value,
                        result_type,
                        expression.location,
                    )
                )
                return value
        target = self._new_value()
        self._emit(
            MirAstFallback(
                target,
                type(expression).__name__,
                result_type,
                expression.location,
            )
        )
        return target


def lower_function_blocks(declaration, typed_report) -> tuple[MirBasicBlock, ...]:
    return _FunctionLowerer(declaration, typed_report).lower()


def instruction_kind(instruction: MirInstruction) -> str:
    name = type(instruction).__name__
    return name.removeprefix("Mir").lower()


def terminator_kind(terminator: MirTerminator) -> str:
    name = type(terminator).__name__
    return name.removeprefix("Mir").lower()


def instruction_contract(instruction: MirInstruction) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": instruction_kind(instruction),
        "line": instruction.location.line,
        "column": instruction.location.column,
    }
    for field in instruction.__dataclass_fields__:
        if field in {"location", "type"}:
            continue
        payload[field] = getattr(instruction, field)
    payload["type"] = render_type(instruction.type)
    return payload


def terminator_contract(terminator: MirTerminator) -> dict[str, object]:
    payload: dict[str, object] = {"kind": terminator_kind(terminator)}
    for field in terminator.__dataclass_fields__:
        payload[field] = getattr(terminator, field)
    return payload


def block_contract(block: MirBasicBlock) -> dict[str, object]:
    return {
        "id": block.id,
        "instructions": [
            instruction_contract(instruction) for instruction in block.instructions
        ],
        "terminator": terminator_contract(block.terminator),
    }


def validate_blocks(blocks: tuple[MirBasicBlock, ...]) -> None:
    if not blocks or blocks[0].id != 0:
        raise ValueError("MIR function must start with basic block 0")
    ids = {block.id for block in blocks}
    if len(ids) != len(blocks):
        raise ValueError("MIR basic block ids must be unique")
    definitions: set[int] = set()
    uses: set[int] = set()
    for block in blocks:
        for instruction in block.instructions:
            target = getattr(instruction, "target", None)
            if target is not None:
                if target in definitions:
                    raise ValueError(f"MIR value %{target} is defined more than once")
                definitions.add(target)
            for name in ("source", "operand", "left", "right", "object", "callee"):
                value = getattr(instruction, name, None)
                if isinstance(value, int):
                    uses.add(value)
            arguments = getattr(instruction, "arguments", ())
            uses.update(value for value in arguments if isinstance(value, int))
        terminator = block.terminator
        if isinstance(terminator, MirJump):
            if terminator.target not in ids:
                raise ValueError(f"MIR jump targets unknown block {terminator.target}")
        elif isinstance(terminator, MirBranch):
            uses.add(terminator.condition)
            if terminator.then_block not in ids or terminator.else_block not in ids:
                raise ValueError("MIR branch targets an unknown block")
        elif isinstance(terminator, MirReturn) and terminator.value is not None:
            uses.add(terminator.value)
    missing = uses - definitions
    if missing:
        raise ValueError(f"MIR uses undefined values: {sorted(missing)}")
