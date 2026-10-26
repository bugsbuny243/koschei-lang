"""Compiler-enforced typestate resources for Koschei.

V1 syntax:

    struct Open {}
    struct Settled {}

    stateful struct Transaction<S> starts Open {
        id: String,
        state: S,
    }

    transition fn settle(tx: Transaction<Open>) -> Transaction<Settled> {
        return Transaction { id: tx.id, state: Settled {} }
    }

Initial-state construction is public. Non-initial state construction is sealed
behind a validated `transition fn`. Stateful values are affine through the A0
ownership checker, so the source owner is consumed at the call boundary and
cannot be used again by the caller.

V1 is deliberately conservative: a transition has one direct stateful source,
one direct final target literal, and cannot hand the source resource elsewhere.
This keeps the state-machine invariant hard while later path-sensitive ownership
work can safely make transition bodies more expressive.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from .ast_nodes import (
    Identifier,
    MemberExpression,
    Program,
    ReturnStatement,
    SourceLocation,
    StructLiteral,
)
from .semantic import ImportedModule, SemanticError
from .type_contracts import (
    TypeContractValidator,
    declaration_type,
    function_type,
    type_parameters_of,
)
from .type_system import (
    GenericType,
    NamedType,
    TypeNode,
    TypeVariable,
    UnionType,
    UnknownType,
    render_type,
    substitute_type,
)
from .typed_hir import TypedHIRReport


_CONTAINER_TYPES = {"List", "Map", "Option", "Result", "BoundedQueue"}


def is_stateful_declaration(declaration) -> bool:
    return bool(getattr(declaration, "is_stateful", False))


def _stateful_declaration(type_node: TypeNode, contracts: TypeContractValidator):
    name = getattr(type_node, "name", None)
    if name is None:
        return None
    declaration = contracts.structs.get(name)
    return declaration if declaration is not None and is_stateful_declaration(declaration) else None


def _stateful_instance(
    type_node: TypeNode, contracts: TypeContractValidator
) -> tuple[object, NamedType] | None:
    if not isinstance(type_node, GenericType):
        return None
    declaration = _stateful_declaration(type_node, contracts)
    if declaration is None or len(type_node.arguments) != 1:
        return None
    marker = type_node.arguments[0]
    if not isinstance(marker, NamedType):
        return None
    return declaration, marker


def is_typestate_affine(
    type_node: TypeNode,
    contracts: TypeContractValidator,
    seen: set[str] | None = None,
) -> bool:
    """Return whether a type owns a stateful resource directly or structurally."""

    seen = set() if seen is None else seen
    if isinstance(type_node, (UnknownType, TypeVariable)):
        return False
    if isinstance(type_node, UnionType):
        return any(is_typestate_affine(item, contracts, seen) for item in type_node.options)

    declaration = _stateful_declaration(type_node, contracts)
    if declaration is not None:
        return True

    if isinstance(type_node, GenericType):
        if any(is_typestate_affine(item, contracts, seen) for item in type_node.arguments):
            return True
        declaration = contracts.structs.get(type_node.name)
        if declaration is None:
            return False
        key = render_type(type_node)
        if key in seen:
            return False
        mapping = dict(zip(type_parameters_of(declaration), type_node.arguments))
        nested_seen = seen | {key}
        return any(
            is_typestate_affine(
                substitute_type(declaration_type(declaration, field.type_ref), mapping),
                contracts,
                nested_seen,
            )
            for field in declaration.fields
        )

    name = getattr(type_node, "name", None)
    if name is None or name in seen:
        return False
    declaration = contracts.structs.get(name)
    if declaration is None:
        return False
    nested_seen = seen | {name}
    return any(
        is_typestate_affine(
            declaration_type(declaration, field.type_ref), contracts, nested_seen
        )
        for field in declaration.fields
    )


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


class TypestateResourceChecker:
    def __init__(
        self,
        program: Program,
        imports: dict[str, ImportedModule],
        typed_report: TypedHIRReport,
    ) -> None:
        self.program = program
        self.imports = imports
        self.typed_report = typed_report
        self.contracts = TypeContractValidator(program, imports)
        self.expression_types = {
            id(item.expression): item.type for item in typed_report.expressions
        }

    def check(self) -> None:
        for declaration in self.program.structs:
            if is_stateful_declaration(declaration):
                self._validate_declaration(declaration)

        # Declarations expose the state contract even if no value is constructed
        # in this module.
        for declaration in self.program.structs:
            if is_stateful_declaration(declaration):
                continue
            for field in declaration.fields:
                self._validate_type(
                    declaration_type(declaration, field.type_ref),
                    field.location,
                    f"'{declaration.name}.{field.name}' alanı",
                )

        for declaration in self.program.enums:
            for variant in declaration.variants:
                if variant.payload_type is None:
                    continue
                payload = declaration_type(declaration, variant.payload_type)
                if is_typestate_affine(payload, self.contracts):
                    raise SemanticError(
                        "KS3952",
                        "Stateful resource enum payload içinde saklanamaz; v1 match "
                        "payload ownership'i partial-move olarak modellemiyor.",
                        variant.location,
                    )
                self._validate_type(
                    payload,
                    variant.location,
                    f"'{declaration.name}.{variant.name}' payload'u",
                )

        for function in self.program.declarations:
            for parameter in function.parameters:
                self._validate_type(
                    function_type(function, parameter.type_ref),
                    parameter.location,
                    f"'{function.name}.{parameter.name}' parametresi",
                )
            if function.return_type is not None:
                self._validate_type(
                    function_type(function, function.return_type),
                    function.return_type.location,
                    f"'{function.name}' dönüş tipi",
                )

            if bool(getattr(function, "is_transition", False)):
                self._validate_transition(function)
            else:
                self._validate_ordinary_construction(function)

        # Inferred state instances from literals/generic substitutions must obey
        # marker/container rules even when the source has no explicit annotation.
        for item in self.typed_report.expressions:
            self._validate_type(item.type, item.expression.location, "ifade")

    def _validate_declaration(self, declaration) -> None:
        parameters = type_parameters_of(declaration)
        if len(parameters) != 1:
            raise SemanticError(
                "KS3950",
                f"stateful struct '{declaration.name}' tam 1 state tip parametresi "
                "istemelidir.",
                declaration.location,
            )
        parameter = parameters[0]
        state_fields = [field for field in declaration.fields if field.name == "state"]
        if len(state_fields) != 1:
            raise SemanticError(
                "KS3950",
                f"stateful struct '{declaration.name}' tam bir 'state: {parameter}' "
                "alanı taşımalıdır.",
                declaration.location,
            )
        state_type = declaration_type(declaration, state_fields[0].type_ref)
        if not isinstance(state_type, TypeVariable) or state_type.name != parameter:
            raise SemanticError(
                "KS3950",
                f"'{declaration.name}.state' doğrudan state parametresi {parameter} "
                "olmalıdır.",
                state_fields[0].location,
            )
        initial = getattr(declaration, "initial_state", None)
        if not initial:
            raise SemanticError(
                "KS3950",
                f"stateful struct '{declaration.name}' 'starts InitialState' ilan etmelidir.",
                declaration.location,
            )
        self._validate_marker(
            NamedType(initial),
            declaration.location,
            f"stateful struct '{declaration.name}' başlangıç state'i",
        )

    def _validate_marker(
        self, marker: TypeNode, location: SourceLocation, subject: str
    ) -> None:
        if not isinstance(marker, NamedType):
            raise SemanticError(
                "KS3951",
                f"{subject}: typestate marker zero-field somut struct olmalıdır.",
                location,
            )
        declaration = self.contracts.structs.get(marker.name)
        if (
            declaration is None
            or declaration.fields
            or type_parameters_of(declaration)
            or is_stateful_declaration(declaration)
        ):
            raise SemanticError(
                "KS3951",
                f"{subject}: '{marker.name}' zero-field, non-generic state-marker "
                "struct olmalıdır.",
                location,
            )

    def _validate_type(
        self, type_node: TypeNode, location: SourceLocation, subject: str
    ) -> None:
        if isinstance(type_node, (UnknownType, TypeVariable, NamedType)):
            return
        if isinstance(type_node, UnionType):
            for option in type_node.options:
                self._validate_type(option, location, subject)
            return
        if not isinstance(type_node, GenericType):
            return

        declaration = _stateful_declaration(type_node, self.contracts)
        if declaration is not None:
            if len(type_node.arguments) != 1:
                raise SemanticError(
                    "KS3950",
                    f"{subject}: stateful {type_node.name} tam 1 state argümanı ister.",
                    location,
                )
            self._validate_marker(type_node.arguments[0], location, subject)
            return

        if type_node.name in _CONTAINER_TYPES and any(
            is_typestate_affine(argument, self.contracts)
            for argument in type_node.arguments
        ):
            raise SemanticError(
                "KS3952",
                f"{subject}: stateful resource {type_node.name} generic container "
                "içinde saklanamaz; container element ownership'i v1'de move-aware değil.",
                location,
            )

        for argument in type_node.arguments:
            self._validate_type(argument, location, subject)

    def _stateful_literals(self, function) -> list[tuple[StructLiteral, object, NamedType]]:
        result: list[tuple[StructLiteral, object, NamedType]] = []
        for node in _walk(function.body):
            if not isinstance(node, StructLiteral):
                continue
            type_node = self.expression_types.get(id(node), UnknownType())
            instance = _stateful_instance(type_node, self.contracts)
            if instance is not None:
                declaration, marker = instance
                result.append((node, declaration, marker))
        return result

    def _validate_ordinary_construction(self, function) -> None:
        for literal, declaration, marker in self._stateful_literals(function):
            initial = getattr(declaration, "initial_state", None)
            if marker.name != initial:
                raise SemanticError(
                    "KS3953",
                    f"'{declaration.name}<{marker.name}>' non-initial state'i normal fn "
                    "içinde doğrudan forge edilemez; '{declaration.name}<{initial}>' "
                    "ile başlayın ve transition fn kullanın.",
                    literal.location,
                )

    def _validate_transition(self, function) -> None:
        if function.name == "main" or function.return_type is None:
            raise SemanticError(
                "KS3953",
                "transition fn main olamaz ve somut stateful dönüş tipi taşımalıdır.",
                function.location,
            )

        return_type = function_type(function, function.return_type)
        target = _stateful_instance(return_type, self.contracts)
        if target is None:
            raise SemanticError(
                "KS3953",
                "transition fn dönüş tipi somut stateful Resource<State> olmalıdır.",
                function.return_type.location,
            )
        target_declaration, target_marker = target
        self._validate_marker(
            target_marker, function.return_type.location, "transition target state"
        )

        sources: list[tuple[object, GenericType, object, NamedType]] = []
        for parameter in function.parameters:
            type_node = function_type(function, parameter.type_ref)
            instance = _stateful_instance(type_node, self.contracts)
            if instance is not None:
                declaration, marker = instance
                sources.append((parameter, type_node, declaration, marker))
        if len(sources) != 1:
            raise SemanticError(
                "KS3953",
                "transition fn v1 tam 1 doğrudan stateful source parametresi almalıdır.",
                function.location,
            )

        source_parameter, source_type, source_declaration, source_marker = sources[0]
        if source_declaration.name != target_declaration.name:
            raise SemanticError(
                "KS3953",
                "transition fn source ve target aynı stateful resource ailesine ait olmalıdır.",
                function.location,
            )
        self._validate_marker(
            source_marker, source_parameter.location, "transition source state"
        )
        if source_marker == target_marker:
            raise SemanticError(
                "KS3953",
                f"transition fn state değiştirmelidir; source ve target ikisi de "
                f"{render_type(source_type)}.",
                function.location,
            )

        statements = function.body.statements
        if not statements or not isinstance(statements[-1], ReturnStatement):
            raise SemanticError(
                "KS3953",
                "transition fn v1 final statement olarak target state'i return etmelidir.",
                function.location,
            )
        final_return = statements[-1]
        if not isinstance(final_return.value, StructLiteral):
            raise SemanticError(
                "KS3953",
                "transition fn v1 final return'da stateful target struct literalini "
                "doğrudan üretmelidir.",
                final_return.location,
            )

        literals = self._stateful_literals(function)
        if len(literals) != 1 or literals[0][0] is not final_return.value:
            raise SemanticError(
                "KS3953",
                "transition fn v1 tam 1 stateful target literal üretmelidir; ara/ek "
                "stateful constructor'lar yasaktır.",
                function.location,
            )
        final_type = self.expression_types.get(id(final_return.value), UnknownType())
        if final_type != return_type:
            raise SemanticError(
                "KS3953",
                f"transition final literal {render_type(return_type)} olmalı, "
                f"{render_type(final_type)} bulundu.",
                final_return.location,
            )

        self._reject_source_escape(
            function.body,
            source_parameter.name,
            function.location,
        )

    def _reject_source_escape(
        self,
        value: Any,
        source_name: str,
        fallback_location: SourceLocation,
        *,
        parent: Any | None = None,
        role: str | None = None,
    ) -> None:
        if isinstance(value, Identifier) and value.name == source_name:
            # Borrowing a field is allowed (`tx.id`). Whole-source use would let
            # the old state escape through another call/alias/return while a new
            # target state is also being minted.
            if isinstance(parent, MemberExpression) and role == "object":
                return
            raise SemanticError(
                "KS3953",
                f"transition source '{source_name}' bütün değer olarak başka yere "
                "move/alias edilemez; yalnız field borrow ile target kurulabilir.",
                value.location,
            )

        if is_dataclass(value):
            for field in fields(value):
                self._reject_source_escape(
                    getattr(value, field.name),
                    source_name,
                    fallback_location,
                    parent=value,
                    role=field.name,
                )
            return
        if isinstance(value, (tuple, list)):
            for item in value:
                self._reject_source_escape(
                    item,
                    source_name,
                    fallback_location,
                    parent=parent,
                    role=role,
                )
            return
        if isinstance(value, dict):
            for item in value.values():
                self._reject_source_escape(
                    item,
                    source_name,
                    fallback_location,
                    parent=parent,
                    role=role,
                )


def check_typestate_resources(
    program: Program,
    imports: dict[str, ImportedModule],
    typed_report: TypedHIRReport,
) -> None:
    TypestateResourceChecker(program, imports, typed_report).check()


def _register_diagnostics() -> None:
    from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic

    entries = {
        "KS3950": (
            "Geçersiz stateful resource bildirimi",
            "Invalid stateful resource declaration",
        ),
        "KS3951": (
            "Geçersiz typestate marker",
            "Invalid typestate marker",
        ),
        "KS3952": (
            "Stateful resource desteklenmeyen container/payload içinde",
            "Stateful resource in unsupported container/payload",
        ),
        "KS3953": (
            "Geçersiz veya forge edilmiş typestate transition",
            "Invalid or forged typestate transition",
        ),
    }
    for code, (tr, en) in entries.items():
        CATALOG.setdefault(
            code,
            Diagnostic(
                code,
                tr,
                tr + ".",
                "Typestate ownership/state transition sözleşmesi fail-closed korundu.",
                "Initial state veya doğrulanmış transition fn üzerinden state değiştirin.",
                "stateful struct Transaction<S> starts Open { state: S }",
            ),
        )
        ENGLISH_CATALOG.setdefault(
            code,
            Diagnostic(
                code,
                en,
                en + ".",
                "The typestate ownership/state-transition contract failed closed.",
                "Use the initial state or a validated transition fn to change state.",
                "stateful struct Transaction<S> starts Open { state: S }",
            ),
        )


_register_diagnostics()
