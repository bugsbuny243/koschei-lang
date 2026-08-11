"""Compiler-enforced typestate resources for Koschei.

V1 uses `stateful struct Resource<S>` where S is a zero-field marker struct.
Stateful resources are affine and transitions are ordinary typed functions that
consume one state and return another. This keeps the state machine in the type
system rather than in runtime booleans/string tags.
"""

from __future__ import annotations

from .ast_nodes import Program, SourceLocation
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
        key = f"{type_node.name}<{','.join(str(item) for item in type_node.arguments)}>"
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

    def check(self) -> None:
        for declaration in self.program.structs:
            if is_stateful_declaration(declaration):
                self._validate_declaration(declaration)

        # Declarations expose the state contract even when no expression creates
        # the resource in this module.
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

        # Typed expressions catch inferred state instances produced by struct
        # literals/generic substitutions rather than only source annotations.
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
    }
    for code, (tr, en) in entries.items():
        CATALOG.setdefault(
            code,
            Diagnostic(
                code,
                tr,
                tr + ".",
                "Typestate ownership/state transition sözleşmesi fail-closed korundu.",
                "State marker ve resource taşıma biçimini v1 typestate kurallarına göre düzeltin.",
                "stateful struct Transaction<S> { state: S }",
            ),
        )
        ENGLISH_CATALOG.setdefault(
            code,
            Diagnostic(
                code,
                en,
                en + ".",
                "The typestate ownership/state-transition contract failed closed.",
                "Fix the marker or resource placement to satisfy typestate v1.",
                "stateful struct Transaction<S> { state: S }",
            ),
        )


_register_diagnostics()
