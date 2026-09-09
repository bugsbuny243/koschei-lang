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
    declaration_type,
    function_type,
    infer_declaration_mapping,
    instantiate_function,
    instantiated_declaration_type,
    require_assignable,
    type_parameters_of,
)
from .type_system import (
    ERROR,
    UNKNOWN,
    VOID,
    GenericType,
    NamedType,
    TypeNode,
    UnknownType,
    alternatives,
    generic,
    is_named,
    parse_type_ref,
    substitute_type,
)


def iterable_success_item_type(type_node: TypeNode) -> TypeNode | None:
    """Project the checked List item type for a for-loop success path.

    A top-level Error alternative is control-flow evidence, not an iterable
    shape.  Typed HIR owns this projection so MIR/runtime consumers never need
    to rediscover or guess it.  Any other ambiguous union remains fail-closed.
    """

    success_options = tuple(option for option in alternatives(type_node) if option != ERROR)
    if len(success_options) != 1:
        return None
    success = success_options[0]
    if isinstance(success, GenericType) and success.name == "List":
        return success.arguments[0] if success.arguments else UNKNOWN
    if is_named(success, "List") or isinstance(success, UnknownType):
        return UNKNOWN
    return None


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
            item_type = iterable_success_item_type(self.infer(statement.iterable))
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
            enum_name, variant_declaration = variant
            enum_declaration = self.enums[enum_name]
            expected = 0 if variant_declaration.payload_type is None else 1
            if len(arguments) != expected:
                raise SemanticError(
                    "KS1301",
                    f"'{name}' constructor'ı {expected} argüman bekler, "
                    f"{len(arguments)} verildi.",
                    location,
                )
            evidence = ()
            if variant_declaration.payload_type is not None:
                evidence = ((variant_declaration.payload_type, arguments[0]),)
            mapping = infer_declaration_mapping(
                enum_declaration,
                evidence,
                location,
                self.contracts,
                subject=f"'{name}' enum constructor'ı",
                allow_missing=True,
            )
            return instantiated_declaration_type(enum_declaration, mapping)
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

        declaration = None
        mapping: dict[str, TypeNode] = {}
        if isinstance(receiver, GenericType):
            declaration = self.structs.get(receiver.name)
            if declaration is not None:
                mapping = dict(zip(type_parameters_of(declaration), receiver.arguments))
        elif isinstance(receiver, NamedType):
            declaration = self.structs.get(receiver.name)

        if declaration is not None:
            for field in declaration.fields:
                if field.name == member:
                    return substitute_type(
                        declaration_type(declaration, field.type_ref), mapping
                    )
        return None

    @staticmethod
    def list_item(type_node: TypeNode) -> TypeNode | None:
        return iterable_success_item_type(type_node)

    def validate_arguments(
        self, function, arguments: tuple[TypeNode, ...], location: SourceLocation
    ) -> TypeNode:
        return instantiate_function(function, arguments, location, self.contracts)

    def struct_literal_type(self, expression) -> TypeNode:
        declaration = self.structs.get(expression.type_name)
        if declaration is None:
            return NamedType(expression.type_name)

        expected_fields = {field.name: field for field in declaration.fields}
        supplied: dict[str, object] = {}
        for name, value in expression.fields:
            if name in supplied:
                raise SemanticError(
                    "KS1501",
                    f"'{expression.type_name}' literalinde '{name}' alanı birden fazla yazılmış.",
                    value.location,
                )
            if name not in expected_fields:
                raise SemanticError(
                    "KS1501",
                    f"'{expression.type_name}' struct'ında '{name}' alanı yok.",
                    value.location,
                )
            supplied[name] = value
        missing = [name for name in expected_fields if name not in supplied]
        if missing:
            raise SemanticError(
                "KS1501",
                f"'{expression.type_name}' literalinde eksik alanlar: {', '.join(missing)}.",
                expression.location,
            )

        actuals = {
            name: self.infer(value) for name, value in supplied.items()
        }
        evidence = tuple(
            (field.type_ref, actuals[field.name]) for field in declaration.fields
        )
        mapping = infer_declaration_mapping(
            declaration,
            evidence,
            expression.location,
            self.contracts,
            subject=f"'{expression.type_name}' struct literal'i",
        )
        for field in declaration.fields:
            expected = substitute_type(
                declaration_type(declaration, field.type_ref), mapping
            )
            require_assignable(
                expected,
                actuals[field.name],
                f"'{expression.type_name}.{field.name}' alanı",
                supplied[field.name].location,
            )
        return instantiated_declaration_type(declaration, mapping)

    def variant_payload(self, value_type: TypeNode, variant: str) -> TypeNode:
        if isinstance(value_type, GenericType):
            if value_type.name == "Option":
                return value_type.arguments[0] if variant == "Some" else UNKNOWN
            if value_type.name == "Result":
                if variant == "Ok":
                    return value_type.arguments[0]
                if variant == "Err":
                    return value_type.arguments[1]
            declaration = self.enums.get(value_type.name)
            if declaration is not None:
                mapping = dict(
                    zip(type_parameters_of(declaration), value_type.arguments)
                )
                for item in declaration.variants:
                    if item.name == variant and item.payload_type is not None:
                        return substitute_type(
                            declaration_type(declaration, item.payload_type), mapping
                        )
        if isinstance(value_type, NamedType):
            declaration = self.enums.get(value_type.name)
            if declaration is not None:
                for item in declaration.variants:
                    if item.name == variant and item.payload_type is not None:
                        return declaration_type(declaration, item.payload_type)
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
