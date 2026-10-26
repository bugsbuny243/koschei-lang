"""AST-free runtime construction rules for ordinary Koschei containers.

This module contains no parser/AST execution authority. It centralizes the runtime
laws needed by staged MIR Map/Struct construction so MirExecutorV1 does not need
to re-interpret source nodes or infer authority from Python object shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .ast_nodes import SourceLocation, StructDeclaration
from .interpreter import KoscheiRuntimeError, StructValue
from .type_contracts import declaration_type
from .type_system import GenericType, NamedType, TypeNode, alternatives, render_type, substitute_type


ContainsCapability = Callable[[Any], bool]
MatchesType = Callable[[Any, tuple[str, ...]], bool]
RuntimeTypeName = Callable[[Any], str]


class ContainerRuntimeError(KoscheiRuntimeError):
    pass


@dataclass(slots=True)
class MapBuilderV1:
    entries: dict[str, Any]
    consumed: bool = False

    @classmethod
    def empty(cls) -> "MapBuilderV1":
        return cls({})

    def insert(
        self,
        key: Any,
        value: Any,
        *,
        contains_capability: ContainsCapability,
        runtime_type_name: RuntimeTypeName,
        location: SourceLocation,
    ) -> None:
        if self.consumed:
            raise ContainerRuntimeError(
                "KS5002", "Consumed MIR Map builder cannot accept inserts.", location
            )
        if not isinstance(key, str):
            raise ContainerRuntimeError(
                "KS3401",
                f"Map anahtarı String olmalıdır, {runtime_type_name(key)} bulundu.",
                location,
            )
        if key in self.entries:
            raise ContainerRuntimeError(
                "KS3101",
                f"Map literalinde '{key}' anahtarı birden fazla yazılmış.",
                location,
            )
        if contains_capability(key) or contains_capability(value):
            raise ContainerRuntimeError(
                "KS3401",
                "Capability taşıyan değerler ordinary Map içine konamaz; runtime type-laundering girişimini reddetti.",
                location,
            )
        self.entries[key] = value

    def finish(self, location: SourceLocation) -> dict[str, Any]:
        if self.consumed:
            raise ContainerRuntimeError(
                "KS5002", "MIR Map builder may be finished exactly once.", location
            )
        self.consumed = True
        return dict(self.entries)


def _require_map_value(value: Any, location: SourceLocation) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContainerRuntimeError(
            "KS5002",
            "Sealed MIR Map value has invalid runtime shape.",
            location,
        )
    return value


def map_get_v1(value: Any, key: Any, location: SourceLocation) -> Any:
    entries = _require_map_value(value, location)
    if not isinstance(key, str):
        raise ContainerRuntimeError(
            "KS5002", "Sealed MIR Map.get key must be String.", location
        )
    if key not in entries:
        from .interpreter import KsError
        return KsError(f"Map anahtarı bulunamadı: {key}")
    return entries[key]


def map_set_v1(
    value: Any,
    key: Any,
    item: Any,
    *,
    contains_capability: ContainsCapability,
    location: SourceLocation,
) -> dict[str, Any]:
    entries = _require_map_value(value, location)
    if not isinstance(key, str):
        raise ContainerRuntimeError(
            "KS5002", "Sealed MIR Map.set key must be String.", location
        )
    if contains_capability(item):
        raise ContainerRuntimeError(
            "KS3401",
            "Capability taşıyan değerler ordinary Map içine konamaz; runtime type-laundering girişimini reddetti.",
            location,
        )

    # Replacement position is a Koschei rule, not host-dict overwrite semantics:
    # an existing key keeps its position; a new key is appended.
    updated: dict[str, Any] = {}
    replaced = False
    for existing_key, existing_value in entries.items():
        if existing_key == key:
            updated[existing_key] = item
            replaced = True
        else:
            updated[existing_key] = existing_value
    if not replaced:
        updated[key] = item
    return updated


def map_keys_v1(value: Any, location: SourceLocation) -> list[str]:
    entries = _require_map_value(value, location)
    return [key for key in entries]


def map_contains_v1(value: Any, key: Any, location: SourceLocation) -> bool:
    entries = _require_map_value(value, location)
    if not isinstance(key, str):
        raise ContainerRuntimeError(
            "KS5002", "Sealed MIR Map.contains key must be String.", location
        )
    return key in entries


@dataclass(slots=True)
class StructBuilderV1:
    declaration: StructDeclaration
    required_fields: tuple[str, ...]
    fields: dict[str, Any]
    concrete_arguments: tuple[TypeNode, ...] | None = None
    consumed: bool = False

    @classmethod
    def empty(
        cls,
        declaration: StructDeclaration,
        required_fields: tuple[str, ...] | None = None,
        location: SourceLocation | None = None,
        concrete_type: TypeNode | None = None,
    ) -> "StructBuilderV1":
        declared = tuple(field.name for field in declaration.fields)
        # Direct container tests and internal callers without a sealed MIR
        # instruction still receive declaration-owned field identity. Public MIR
        # execution passes required_fields explicitly and therefore remains bound
        # to the compiler product.
        required_fields = declared if required_fields is None else required_fields
        location = declaration.location if location is None else location
        if len(required_fields) != len(set(required_fields)):
            raise ContainerRuntimeError(
                "KS5002", "Sealed MIR Struct required_fields contains duplicates.", location
            )
        if set(required_fields) != set(declared):
            raise ContainerRuntimeError(
                "KS5002",
                "Sealed MIR Struct required_fields disagrees with checked declaration.",
                location,
            )
        concrete_arguments: tuple[TypeNode, ...] | None = None
        if concrete_type is not None:
            candidates = tuple(
                option
                for option in alternatives(concrete_type)
                if isinstance(option, (NamedType, GenericType))
                and option.name == declaration.name
            )
            if len(candidates) != 1:
                raise ContainerRuntimeError(
                    "KS5002",
                    "Sealed MIR Struct concrete type does not identify exactly one checked declaration instance.",
                    location,
                )
            selected = candidates[0]
            concrete_arguments = selected.arguments if isinstance(selected, GenericType) else ()
            parameters = tuple(getattr(declaration, "type_parameters", ()))
            if len(concrete_arguments) != len(parameters):
                raise ContainerRuntimeError(
                    "KS5002",
                    "Sealed MIR Struct generic arity disagrees with checked declaration.",
                    location,
                )
        return cls(
            declaration,
            required_fields,
            {},
            concrete_arguments=concrete_arguments,
        )

    def set_field(
        self,
        name: str,
        value: Any,
        *,
        contains_capability: ContainsCapability,
        matches_type: MatchesType,
        runtime_type_name: RuntimeTypeName,
        location: SourceLocation,
    ) -> None:
        if self.consumed:
            raise ContainerRuntimeError(
                "KS5002", "Consumed MIR Struct builder cannot accept fields.", location
            )
        if name not in self.required_fields:
            raise ContainerRuntimeError(
                "KS5002",
                f"Sealed MIR Struct did not admit field '{name}'.",
                location,
            )
        if name in self.fields:
            raise ContainerRuntimeError(
                "KS5002",
                f"Sealed MIR Struct field '{name}' was assigned more than once.",
                location,
            )
        expected = {field.name: field for field in self.declaration.fields}
        field = expected.get(name)
        if field is None:
            raise ContainerRuntimeError(
                "KS3101",
                f"'{self.declaration.name}' struct'ında '{name}' alanı yok.",
                location,
            )
        if contains_capability(value):
            raise ContainerRuntimeError(
                "KS3401",
                "Capability taşıyan değerler ordinary Struct içine konamaz; runtime type-laundering girişimini reddetti.",
                location,
            )
        expected_names = field.type_ref.names
        if self.concrete_arguments is not None:
            parameters = tuple(getattr(self.declaration, "type_parameters", ()))
            mapping = dict(zip(parameters, self.concrete_arguments))
            expected_type = substitute_type(
                declaration_type(self.declaration, field.type_ref),
                mapping,
            )
            expected_names = (render_type(expected_type),)
        if not matches_type(value, expected_names):
            raise ContainerRuntimeError(
                "KS3401",
                f"'{self.declaration.name}.{name}' alanı {' or '.join(expected_names)} beklerken {runtime_type_name(value)} aldı.",
                location,
            )
        self.fields[name] = value

    def finish(self, location: SourceLocation | None = None) -> StructValue:
        location = self.declaration.location if location is None else location
        if self.consumed:
            raise ContainerRuntimeError(
                "KS5002", "MIR Struct builder may be finished exactly once.", location
            )
        expected_names = set(self.required_fields)
        actual_names = set(self.fields)
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)
            detail = []
            if missing:
                detail.append("eksik=" + ",".join(missing))
            if extra:
                detail.append("fazla=" + ",".join(extra))
            raise ContainerRuntimeError(
                "KS3101",
                f"'{self.declaration.name}' struct alan sözleşmesi tamamlanmadı ({'; '.join(detail)}).",
                location,
            )
        self.consumed = True
        ordered = {name: self.fields[name] for name in self.required_fields}
        type_arguments = (
            tuple(render_type(item) for item in self.concrete_arguments)
            if self.concrete_arguments is not None
            else ()
        )
        return StructValue(self.declaration.name, ordered, type_arguments)
