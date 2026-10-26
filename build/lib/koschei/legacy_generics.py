"""Monomorphized compatibility view for the legacy semantic checker.

The runtime and native backend still consume the original generic AST. This
module gives the v0.9 semantic pass concrete call signatures so it can continue
enforcing scopes, immutability, error handling and capabilities while Typed HIR
owns generic type inference.
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from .ast_nodes import (
    AssignmentExpression,
    BinaryExpression,
    Block,
    CallExpression,
    ExpressionStatement,
    ForStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    InterpolatedString,
    LetStatement,
    ListLiteral,
    MapLiteral,
    MatchArm,
    MatchExpression,
    MemberExpression,
    OrBlockExpression,
    OrElseExpression,
    OrReturnExpression,
    Parameter,
    Program,
    ReturnStatement,
    StructLiteral,
    TypeRef,
    UnaryExpression,
    WhileStatement,
)
from .generic_nodes import GenericFunctionDeclaration
from .legacy_types import erase_function, erase_imports, erase_program
from .semantic import ImportedModule
from .type_contracts import function_type, infer_function_mapping
from .type_system import (
    TypeNode,
    UnionType,
    UnknownType,
    alternatives,
    render_type,
    substitute_type,
    unresolved_type_variables,
)


def _type_ref(type_node: TypeNode, location) -> TypeRef:
    if isinstance(type_node, UnknownType):
        names = ("_",)
    elif isinstance(type_node, UnionType):
        names = tuple(render_type(item) for item in alternatives(type_node))
    else:
        names = (render_type(type_node),)
    return TypeRef(names, location)


def _specialized_name(function, mapping: dict[str, TypeNode]) -> str:
    signature = ";".join(
        f"{name}={render_type(mapping[name])}" for name in function.type_parameters
    )
    digest = sha256(signature.encode("utf-8")).hexdigest()[:12]
    return f"__ksg_{function.name}_{digest}"


def _specialize(function, mapping: dict[str, TypeNode], name: str) -> FunctionDeclaration:
    parameters = tuple(
        Parameter(
            parameter.name,
            _type_ref(
                substitute_type(function_type(function, parameter.type_ref), mapping),
                parameter.type_ref.location,
            ),
            parameter.location,
        )
        for parameter in function.parameters
    )
    return_type = None
    if function.return_type is not None:
        concrete = substitute_type(function_type(function, function.return_type), mapping)
        unresolved = unresolved_type_variables(concrete)
        if unresolved:
            raise AssertionError(
                f"unresolved specialization for {function.name}: {sorted(unresolved)}"
            )
        return_type = _type_ref(concrete, function.return_type.location)
    return GenericFunctionDeclaration(
        name, parameters, return_type, function.body, function.location, ()
    )


class _Rewriter:
    def __init__(self, program, imports, report) -> None:
        self.program = program
        self.imports = imports
        self.functions = {item.name: item for item in program.declarations}
        self.types = {id(item.expression): item.type for item in report.expressions}
        self.local_specs: dict[str, FunctionDeclaration] = {}
        self.import_specs: dict[str, dict[str, FunctionDeclaration]] = {}

    def rewrite(self) -> tuple[Program, dict[str, dict[str, FunctionDeclaration]]]:
        declarations: list[FunctionDeclaration] = []
        for function in self.program.declarations:
            if function.type_parameters:
                declarations.append(function)
            else:
                declarations.append(replace(function, body=self.block(function.body)))
        declarations.extend(self.local_specs.values())
        return replace(self.program, declarations=tuple(declarations)), self.import_specs

    def block(self, block: Block) -> Block:
        return Block(tuple(self.statement(item) for item in block.statements))

    def statement(self, statement):
        if isinstance(statement, LetStatement):
            return replace(statement, value=self.expression(statement.value))
        if isinstance(statement, ReturnStatement):
            return replace(
                statement,
                value=None if statement.value is None else self.expression(statement.value),
            )
        if isinstance(statement, ExpressionStatement):
            return replace(statement, expression=self.expression(statement.expression))
        if isinstance(statement, IfStatement):
            branch = statement.else_branch
            if isinstance(branch, Block):
                branch = self.block(branch)
            elif isinstance(branch, IfStatement):
                branch = self.statement(branch)
            return replace(
                statement,
                condition=self.expression(statement.condition),
                then_block=self.block(statement.then_block),
                else_branch=branch,
            )
        if isinstance(statement, WhileStatement):
            return replace(
                statement,
                condition=self.expression(statement.condition),
                body=self.block(statement.body),
            )
        if isinstance(statement, ForStatement):
            return replace(
                statement,
                iterable=self.expression(statement.iterable),
                body=self.block(statement.body),
            )
        raise AssertionError(type(statement).__name__)

    def expression(self, expression):
        if isinstance(expression, Identifier):
            return expression
        from .ast_nodes import Literal

        if isinstance(expression, Literal):
            return expression
        if isinstance(expression, InterpolatedString):
            return replace(
                expression,
                parts=tuple(self.expression(item) for item in expression.parts),
            )
        if isinstance(expression, ListLiteral):
            return replace(
                expression,
                items=tuple(self.expression(item) for item in expression.items),
            )
        if isinstance(expression, MapLiteral):
            return replace(
                expression,
                entries=tuple(
                    (self.expression(key), self.expression(value))
                    for key, value in expression.entries
                ),
            )
        if isinstance(expression, StructLiteral):
            return replace(
                expression,
                fields=tuple(
                    (name, self.expression(value)) for name, value in expression.fields
                ),
            )
        if isinstance(expression, MemberExpression):
            return replace(expression, object=self.expression(expression.object))
        if isinstance(expression, CallExpression):
            arguments = tuple(self.expression(item) for item in expression.arguments)
            callee = self.expression(expression.callee)
            original_types = tuple(
                self.types.get(id(item), UnknownType()) for item in expression.arguments
            )
            if isinstance(expression.callee, Identifier):
                function = self.functions.get(expression.callee.name)
                if function is not None and function.type_parameters:
                    mapping = infer_function_mapping(
                        function, original_types, expression.location
                    )
                    name = _specialized_name(function, mapping)
                    self.local_specs.setdefault(name, _specialize(function, mapping, name))
                    callee = Identifier(name, expression.callee.location)
            elif (
                isinstance(expression.callee, MemberExpression)
                and isinstance(expression.callee.object, Identifier)
            ):
                alias = expression.callee.object.name
                module = self.imports.get(alias)
                function = None if module is None else module.functions.get(
                    expression.callee.member
                )
                if function is not None and function.type_parameters:
                    mapping = infer_function_mapping(
                        function, original_types, expression.location
                    )
                    name = _specialized_name(function, mapping)
                    self.import_specs.setdefault(alias, {}).setdefault(
                        name, _specialize(function, mapping, name)
                    )
                    callee = replace(callee, member=name)
            return replace(expression, callee=callee, arguments=arguments)
        if isinstance(expression, AssignmentExpression):
            return replace(
                expression,
                target=self.expression(expression.target),
                value=self.expression(expression.value),
            )
        if isinstance(expression, BinaryExpression):
            return replace(
                expression,
                left=self.expression(expression.left),
                right=self.expression(expression.right),
            )
        if isinstance(expression, UnaryExpression):
            return replace(expression, operand=self.expression(expression.operand))
        if isinstance(expression, OrReturnExpression):
            return replace(
                expression,
                value=self.expression(expression.value),
                error=None if expression.error is None else self.expression(expression.error),
            )
        if isinstance(expression, OrElseExpression):
            return replace(
                expression,
                value=self.expression(expression.value),
                fallback=self.expression(expression.fallback),
            )
        if isinstance(expression, OrBlockExpression):
            return replace(
                expression,
                value=self.expression(expression.value),
                handler=self.block(expression.handler),
            )
        if isinstance(expression, MatchExpression):
            return replace(
                expression,
                value=self.expression(expression.value),
                arms=tuple(
                    MatchArm(
                        arm.variant,
                        arm.binding,
                        self.expression(arm.body),
                        arm.location,
                    )
                    for arm in expression.arms
                ),
            )
        raise AssertionError(type(expression).__name__)


def prepare_legacy_analysis(
    program: Program,
    imports: dict[str, ImportedModule],
    typed_report,
) -> tuple[Program, dict[str, ImportedModule]]:
    rewritten, import_specs = _Rewriter(program, imports, typed_report).rewrite()
    legacy_program = erase_program(rewritten)
    legacy_imports = erase_imports(imports)
    for alias, functions in import_specs.items():
        module = legacy_imports[alias]
        merged = dict(module.functions)
        merged.update({name: erase_function(item) for name, item in functions.items()})
        legacy_imports[alias] = ImportedModule(
            module.name, merged, module.structs, module.enums
        )
    return legacy_program, legacy_imports
