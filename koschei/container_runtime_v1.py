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


ContainsCapability = Callable[[Any], bool]
MatchesType = Callable[[Any, tuple[str, ...]], bool]
RuntimeTypeName = Callable[[Any], str]


class ContainerRuntimeError(KoscheiRuntimeError):
    pass


@dataclass(slots=True)
class MapBuilderV1:
    entries: dict[str, Any]

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

    def finish(self) -> dict[str, Any]:
        return self.entries


@dataclass(slots=True)
class StructBuilderV1:
    declaration: StructDeclaration
    fields: dict[str, Any]

    @classmethod
    def empty(cls, declaration: StructDeclaration) -> "StructBuilderV1":
        return cls(declaration, {})

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
        if not matches_type(value, field.type_ref.names):
            raise ContainerRuntimeError(
                "KS3401",
                f"'{self.declaration.name}.{name}' alanı {field.type_ref} beklerken {runtime_type_name(value)} aldı.",
                location,
            )
        self.fields[name] = value

    def finish(self) -> StructValue:
        expected_names = {field.name for field in self.declaration.fields}
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
                self.declaration.location,
            )
        return StructValue(self.declaration.name, dict(self.fields))
