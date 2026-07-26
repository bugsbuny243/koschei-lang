"""First backend-independent Typed HIR slice for Koschei V5."""

from __future__ import annotations

from dataclasses import dataclass

from . import _typed_ops as _typed_ops_registration

from .ast_nodes import (
    Block,
    Expression,
    ExpressionStatement,
    ForStatement,
    IfStatement,
    LetStatement,
    Program,
    ReturnStatement,
    SourceLocation,
    Statement,
    WhileStatement,
)
from .semantic import ImportedModule, SemanticError
from .type_contracts import (
    TypeContractValidator,
    function_type,
    instantiate_function,
    require_assignable,
)
from .type_system import (
    ERROR,
    UNKNOWN,
    VOID,
    GenericType,
    NamedType,
    TypeNode,
    UnknownType,
    generic,
    is_named,
    parse_type_ref,
)


@dataclass(frozen=True, slots=True)
class TypedBinding:
    name: str
    type: TypeNode
    location: SourceLocation
    role: str


@dataclass(frozen=True, slots=True)
class TypedExpression:
    expression: Expression
    type: TypeNode


@dataclass(frozen=True, slots=True)
class TypedHIRReport:
    bindings: tuple[TypedBinding, ...]
    expressions: tuple[TypedExpression, ...]
    collections: int

    def binding_types(self, name: str) -> tuple[TypeNode, ...]:
        return tuple(item.type for item in self.bindings if item.name == name)


class TypedHIRChecker:
    def __init__(
        self,
        program: Program,
        imports: dict[str, ImportedModule] | None = None,
    ) -> None:
        self.program = program
        self.imports = imports or {}
        self.functions = {item.name: item for item in program.declarations}
        self.structs = {item.name: item for item in program.structs}
        self.enums = {item.name: item for item in program.enums}
        self.variants = {
            variant.name: (declaration.name, variant)
            for declaration in program.enums
            for variant in declaration.variants
        }
        for module in self.imports.values():
            for name, declaration in module.structs.items():
                self.structs.setdefault(name, declaration)
            for name, declaration in module.enums.items():
                self.enums.setdefault(name, declaration)
                for variant in declaration.variants:
                    self.variants.setdefault(variant.name, (name, variant))
        self.scopes: list[dict[str, TypeNode]] = []
        self.bindings: list[TypedBinding] = []
        self.expressions: list[TypedExpression] = []
        self.collections = 0
        self.current_function = None
        self.contracts = TypeContractValidator(program, self.imports)

    def check(self) -> TypedHIRReport:
        self.contracts.validate()
        for function in self.program.declarations:
            self.current_function = function
            self.scopes.append({})
            try:
                for parameter in function.parameters:
                    self.declare(
                        parameter.name,
                        function_type(function, parameter.type_ref),
                        parameter.location,
                        "parameter",
                    )
                self.check_block(function.body, nested=False)
            finally:
                self.scopes.pop()
                self.current_function = None
        return TypedHIRReport(
            tuple(self.bindings), tuple(self.expressions), self.collections
        )

    def declare(
        self, name: str, type_node: TypeNode, location: SourceLocation, role: str
    ) -> None:
        self.scopes[-1][name] = type_node
        self.bindings.append(TypedBinding(name, type_node, location, role))

    def resolve(self, name: str) -> TypeNode:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return UNKNOWN

    def record(self, expression: Expression, type_node: TypeNode) -> TypeNode:
        self.expressions.append(TypedExpression(expression, type_node))
        return type_node

    def infer(self, expression: Expression) -> TypeNode:
        from ._typed_expr import infer_expression

        return infer_expression(self, expression)

    def check_block(self, block: Block, *, nested: bool = True) -> None:
        if nested:
            self.scopes.append({})
        try:
            for statement in block.statements:
                self.check_statement(statement)
        finally:
            if nested:
                self.scopes.pop()

    def check_statement(self, statement: Statement) -> None:
        if isinstance(statement, LetStatement):
            self.declare(
                statement.name,
                self.infer(statement.value),
                statement.location,
                "local",
            )
        elif isinstance(statement, ReturnStatement):
            if statement.value is not None:
                actual = self.infer(statement.value)
                if (
                    self.current_function is not None
                    and self.current_function.return_type is not None
                ):
                    require_assignable(
                        function_type(
                            self.current_function,
                            self.current_function.return_type,
                        ),
                        actual,
                        f"'{self.current_function.name}' dönüş değeri",
                        statement.location,
                    )
        elif isinstance(statement, ExpressionStatement):
            self.infer(statement.expression)
        elif isinstance(statement, IfStatement):
            self.infer(statement.condition)
            self.check_block(statement.then_block)
            if isinstance(statement.else_branch, Block):
                self.check_block(statement.else_branch)
            elif isinstance(statement.else_branch, IfStatement):
                self.check_statement(statement.else_branch)
        elif isinstance(statement, WhileStatement):
            self.infer(statement.condition)
            self.check_block(statement.body)
        elif isinstance(statement, ForStatement):
            item_type = self.list_item(self.infer(statement.iterable))
            if item_type is None:
                return
            self.scopes.append({})
            try:
                self.declare(
                    statement.variable,
                    item_type,
                    statement.location,
                    "for-item",
                )
                self.check_block(statement.body, nested=False)
            finally:
                self.scopes.pop()
        else:
            raise AssertionError(type(statement).__name__)

    def call_type(
        self,
        name: str,
        arguments: tuple[TypeNode, ...],
        location: SourceLocation,
    ) -> TypeNode:
        function = self.functions.get(name)
        if function is not None:
            return instantiate_function(function, arguments, location, self.contracts)
        variant = self.variants.get(name)
        if variant is not None:
            enum_name, declaration = variant
            expected = 0 if declaration.payload_type is None else 1
            if len(arguments) != expected:
                raise SemanticError(
                    "KS1301",
                    f"'{name}' constructor'ı {expected} argüman bekler, "
                    f"{len(arguments)} verildi.",
                    location,
                )
            if declaration.payload_type is not None:
                require_assignable(
                    parse_type_ref(declaration.payload_type),
                    arguments[0],
                    f"'{name}' payload'u",
                    location,
                )
            return NamedType(enum_name)
        if name == "Some":
            return generic("Option", arguments[0] if arguments else UNKNOWN)
        if name == "None":
            return generic("Option", UNKNOWN)
        if name == "Ok":
            return generic("Result", arguments[0] if arguments else UNKNOWN, UNKNOWN)
        if name == "Err":
            return generic("Result", UNKNOWN, arguments[0] if arguments else ERROR)
        if name == "Error":
            return ERROR
        if name in {"print", "println"}:
            return VOID
        return UNKNOWN

    def module_call_type(
        self,
        receiver: TypeNode,
        member: str,
        arguments: tuple[TypeNode, ...] | None = None,
        location: SourceLocation | None = None,
    ) -> TypeNode | None:
        if not isinstance(receiver, NamedType) or not receiver.name.startswith("Module:"):
            return None
        module = self.imports.get(receiver.name.split(":", 1)[1])
        if module is None:
            return UNKNOWN
        function = module.functions.get(member)
        if function is not None:
            if arguments is None or location is None:
                return function_type(function, function.return_type)
            return instantiate_function(function, arguments, location, self.contracts)
        if member in module.structs or member in module.enums:
            return NamedType(member)
        return UNKNOWN

    def field_type(self, receiver: TypeNode, member: str) -> TypeNode | None:
        if isinstance(receiver, NamedType) and receiver.name == "SystemCaps":
            from .semantic import CAPABILITY_MEMBERS

            capability = CAPABILITY_MEMBERS.get(member)
            if capability is not None:
                return NamedType(capability)
        module_type = self.module_call_type(receiver, member)
        if module_type is not None:
            return module_type
        if isinstance(receiver, NamedType):
            declaration = self.structs.get(receiver.name)
            if declaration is not None:
                for field in declaration.fields:
                    if field.name == member:
                        return parse_type_ref(field.type_ref)
        return None

    @staticmethod
    def list_item(type_node: TypeNode) -> TypeNode | None:
        if isinstance(type_node, GenericType) and type_node.name == "List":
            return type_node.arguments[0] if type_node.arguments else UNKNOWN
        if is_named(type_node, "List") or isinstance(type_node, UnknownType):
            return UNKNOWN
        return None

    def validate_arguments(
        self, function, arguments: tuple[TypeNode, ...], location: SourceLocation
    ) -> TypeNode:
        return instantiate_function(function, arguments, location, self.contracts)

    def struct_literal_type(self, expression) -> TypeNode:
        declaration = self.structs.get(expression.type_name)
        if declaration is None:
            return NamedType(expression.type_name)
        supplied = {name: value for name, value in expression.fields}
        for field in declaration.fields:
            value = supplied.get(field.name)
            if value is not None:
                require_assignable(
                    parse_type_ref(field.type_ref),
                    self.infer(value),
                    f"'{expression.type_name}.{field.name}' alanı",
                    value.location,
                )
        return NamedType(expression.type_name)

    def variant_payload(self, value_type: TypeNode, variant: str) -> TypeNode:
        if isinstance(value_type, GenericType):
            if value_type.name == "Option":
                return value_type.arguments[0] if variant == "Some" else UNKNOWN
            if value_type.name == "Result":
                if variant == "Ok":
                    return value_type.arguments[0]
                if variant == "Err":
                    return value_type.arguments[1]
        if isinstance(value_type, NamedType):
            declaration = self.enums.get(value_type.name)
            if declaration is not None:
                for item in declaration.variants:
                    if item.name == variant and item.payload_type is not None:
                        return parse_type_ref(item.payload_type)
        return UNKNOWN


def lower_typed_hir(
    program: Program,
    imports: dict[str, ImportedModule] | None = None,
) -> TypedHIRReport:
    return TypedHIRChecker(program, imports).check()


def check_typed_hir(
    program: Program,
    imports: dict[str, ImportedModule] | None = None,
) -> TypedHIRReport:
    return lower_typed_hir(program, imports)
