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
    MatchArm,
    MatchExpression,
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
    STRING,
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
    shape. Typed HIR owns this projection so MIR/runtime consumers never need
    to rediscover or guess it. Any other ambiguous union remains fail-closed.
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
class TypedMatchArmResolution:
    """One compiler-authoritative match-arm identity.

    ``canonical_variant`` is never reconstructed by MIR or a backend. It is
    emitted only after Typed HIR resolved the scrutinee type against the enum
    declaration/builtin sum type that owns the visible arm name.
    """

    arm: MatchArm
    owner: str
    variant: str
    canonical_variant: str
    payload_type: TypeNode | None
    binding_type: TypeNode | None


@dataclass(frozen=True, slots=True)
class TypedMatchResolution:
    expression: MatchExpression
    value_type: TypeNode
    arms: tuple[TypedMatchArmResolution, ...]
    exhaustive: bool


@dataclass(frozen=True, slots=True)
class TypedStructLiteralResolution:
    expression: Expression
    type_name: str
    required_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TypedMapLiteralResolution:
    expression: Expression
    key_type: TypeNode
    duplicate_policy: str


@dataclass(frozen=True, slots=True)
class TypedMapMethodResolution:
    expression: Expression
    receiver_type: TypeNode
    method: str


@dataclass(frozen=True, slots=True)
class TypedHIRReport:
    bindings: tuple[TypedBinding, ...]
    expressions: tuple[TypedExpression, ...]
    collections: int
    match_resolutions: tuple[TypedMatchResolution, ...] = ()
    struct_literal_resolutions: tuple[TypedStructLiteralResolution, ...] = ()
    map_literal_resolutions: tuple[TypedMapLiteralResolution, ...] = ()
    map_method_resolutions: tuple[TypedMapMethodResolution, ...] = ()

    def binding_types(self, name: str) -> tuple[TypeNode, ...]:
        return tuple(item.type for item in self.bindings if item.name == name)

    def match_resolution_of(
        self, expression: MatchExpression
    ) -> TypedMatchResolution | None:
        for item in self.match_resolutions:
            if item.expression is expression:
                return item
        return None

    def struct_literal_resolution_of(self, expression) -> TypedStructLiteralResolution | None:
        for item in self.struct_literal_resolutions:
            if item.expression is expression:
                return item
        return None

    def map_literal_resolution_of(self, expression) -> TypedMapLiteralResolution | None:
        for item in self.map_literal_resolutions:
            if item.expression is expression:
                return item
        return None

    def map_method_resolution_of(self, expression) -> TypedMapMethodResolution | None:
        for item in self.map_method_resolutions:
            if item.expression is expression:
                return item
        return None


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
        self.match_resolutions: list[TypedMatchResolution] = []
        self.struct_literal_resolutions: list[TypedStructLiteralResolution] = []
        self.map_literal_resolutions: list[TypedMapLiteralResolution] = []
        self.map_method_resolutions: list[TypedMapMethodResolution] = []
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
            tuple(self.bindings),
            tuple(self.expressions),
            self.collections,
            tuple(self.match_resolutions),
            tuple(self.struct_literal_resolutions),
            tuple(self.map_literal_resolutions),
            tuple(self.map_method_resolutions),
        )

    def record_map_literal_resolution(self, expression: Expression) -> None:
        self.map_literal_resolutions.append(
            TypedMapLiteralResolution(expression, STRING, "reject")
        )

    def record_map_method_resolution(
        self,
        expression: Expression,
        receiver_type: TypeNode,
        method: str,
    ) -> None:
        if (
            isinstance(receiver_type, GenericType)
            and receiver_type.name == "Map"
        ) or is_named(receiver_type, "Map"):
            self.map_method_resolutions.append(
                TypedMapMethodResolution(expression, receiver_type, method)
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
        required_fields = tuple(field.name for field in declaration.fields)
        self.struct_literal_resolutions.append(
            TypedStructLiteralResolution(expression, declaration.name, required_fields)
        )
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

        actuals = {name: self.infer(value) for name, value in supplied.items()}
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

    def resolve_match_variant(
        self, value_type: TypeNode, variant: str
    ) -> tuple[str, TypeNode | None, tuple[str, ...]] | None:
        """Resolve a visible arm name to its canonical owner and payload.

        This is the single Typed-HIR authority for match identity. Consumers
        must use the emitted ``Owner::Variant`` fact rather than guessing an
        owner from the source-visible variant token.
        """

        if isinstance(value_type, GenericType):
            if value_type.name == "Option":
                if variant == "Some":
                    payload = value_type.arguments[0] if value_type.arguments else UNKNOWN
                    return "Option", payload, ("Some", "None")
                if variant == "None":
                    return "Option", None, ("Some", "None")
                return None
            if value_type.name == "Result":
                if variant == "Ok":
                    payload = value_type.arguments[0] if value_type.arguments else UNKNOWN
                    return "Result", payload, ("Ok", "Err")
                if variant == "Err":
                    payload = value_type.arguments[1] if len(value_type.arguments) > 1 else ERROR
                    return "Result", payload, ("Ok", "Err")
                return None
            declaration = self.enums.get(value_type.name)
            if declaration is not None:
                mapping = dict(zip(type_parameters_of(declaration), value_type.arguments))
                expected = tuple(item.name for item in declaration.variants)
                for item in declaration.variants:
                    if item.name != variant:
                        continue
                    payload = None
                    if item.payload_type is not None:
                        payload = substitute_type(
                            declaration_type(declaration, item.payload_type), mapping
                        )
                    return declaration.name, payload, expected
                return None

        if isinstance(value_type, NamedType):
            if value_type.name == "Option":
                if variant == "Some":
                    return "Option", UNKNOWN, ("Some", "None")
                if variant == "None":
                    return "Option", None, ("Some", "None")
                return None
            if value_type.name == "Result":
                if variant == "Ok":
                    return "Result", UNKNOWN, ("Ok", "Err")
                if variant == "Err":
                    return "Result", ERROR, ("Ok", "Err")
                return None
            declaration = self.enums.get(value_type.name)
            if declaration is not None:
                expected = tuple(item.name for item in declaration.variants)
                for item in declaration.variants:
                    if item.name != variant:
                        continue
                    payload = (
                        declaration_type(declaration, item.payload_type)
                        if item.payload_type is not None
                        else None
                    )
                    return declaration.name, payload, expected
                return None
        return None

    def record_match_resolution(
        self,
        expression: MatchExpression,
        value_type: TypeNode,
        arm_rows: list[
            tuple[
                MatchArm,
                tuple[str, TypeNode | None, tuple[str, ...]] | None,
                TypeNode | None,
            ]
        ],
    ) -> None:
        if not arm_rows or any(resolution is None for _, resolution, _ in arm_rows):
            return

        owners = {resolution[0] for _, resolution, _ in arm_rows if resolution is not None}
        if len(owners) != 1:
            return

        resolved_arms: list[TypedMatchArmResolution] = []
        expected_variants: tuple[str, ...] | None = None
        for arm, resolution, binding_type in arm_rows:
            if resolution is None:
                return
            owner, payload_type, expected = resolution
            if expected_variants is None:
                expected_variants = expected
            elif expected_variants != expected:
                return
            resolved_arms.append(
                TypedMatchArmResolution(
                    arm=arm,
                    owner=owner,
                    variant=arm.variant,
                    canonical_variant=f"{owner}::{arm.variant}",
                    payload_type=payload_type,
                    binding_type=binding_type,
                )
            )

        seen = {item.variant for item in resolved_arms}
        exhaustive = bool(expected_variants) and set(expected_variants).issubset(seen)
        self.match_resolutions.append(
            TypedMatchResolution(
                expression=expression,
                value_type=value_type,
                arms=tuple(resolved_arms),
                exhaustive=exhaustive,
            )
        )

    def variant_payload(self, value_type: TypeNode, variant: str) -> TypeNode:
        resolution = self.resolve_match_variant(value_type, variant)
        if resolution is None:
            return UNKNOWN
        _, payload_type, _ = resolution
        return UNKNOWN if payload_type is None else payload_type


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
