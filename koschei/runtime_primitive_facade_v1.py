"""Narrow runtime primitive ABI for sealed MIR execution.

The MIR executor may reuse existing runtime value/capability implementations, but
it must not acquire the reference interpreter's AST execution authority or carry
raw interpreter callable objects across the MIR/runtime boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ast_nodes import FunctionDeclaration, Program, SourceLocation
from .container_runtime_v1 import MapBuilderV1, StructBuilderV1
from .interpreter import (
    DiskCaps,
    DiskReadCaps,
    DiskRoot,
    EnvCaps,
    EnvRoot,
    Interpreter,
    KsError,
    KoscheiRuntimeError,
    ModuleFunction,
    NetCaps,
    NetRoot,
    ProcessCaps,
    ProcessRoot,
    Response,
    _BoundMember,
    _EnumConstructor,
    _contains_capability,
    ks_to_string,
)


class RuntimePrimitiveFacadeError(KoscheiRuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _PrimitiveMemberRefV1:
    """Facade-owned opaque reference to one already-authorized primitive member."""

    raw: _BoundMember


@dataclass(frozen=True, slots=True)
class _PrimitiveConstructorRefV1:
    """Facade-owned opaque reference to one canonical enum/Option/Result constructor."""

    raw: _EnumConstructor


class RuntimePrimitiveFacadeV1:
    """AST-opaque primitive surface consumed by ``MirExecutorV1``."""

    __slots__ = ("_runtime",)

    _BUILTIN_CALLS = frozenset({"print", "println", "Error"})
    _STRING_MEMBERS = frozenset(
        {"length", "to_int", "to_float", "contains", "trim", "split", "join"}
    )
    _LIST_MEMBERS = frozenset({"length", "get", "push", "contains", "sort", "filter"})
    _MAP_MEMBERS = frozenset({"get", "set", "keys", "contains"})
    _TYPED_MEMBER_ALLOWLIST = {
        NetRoot: frozenset({"allow"}),
        DiskRoot: frozenset({"allow", "allow_read_only"}),
        EnvRoot: frozenset({"allow"}),
        ProcessRoot: frozenset({"allow"}),
        NetCaps: frozenset({"get", "post", "put", "delete", "request"}),
        DiskCaps: frozenset({"read", "read_file", "write", "write_file", "list", "delete"}),
        DiskReadCaps: frozenset({"read", "read_file", "write", "write_file", "list", "delete"}),
        EnvCaps: frozenset({"get"}),
        ProcessCaps: frozenset({"run", "spawn"}),
        Response: frozenset({"text", "status"}),
    }

    def __init__(
        self,
        program: Program,
        argv: list[str],
        *,
        namespaces,
        imports,
        enums,
        module_imports,
        structs,
    ) -> None:
        self._runtime = Interpreter(
            program,
            argv,
            namespaces=namespaces,
            imports=imports,
            enums=enums,
            module_imports=module_imports,
            structs=structs,
        )

    def constructor(self, name: str):
        raw = self._runtime.constructors.get(name)
        if raw is None:
            return None
        if not isinstance(raw, _EnumConstructor):
            raise RuntimePrimitiveFacadeError(
                "KS5002",
                f"MIR primitive constructor allowlist dışı: '{name}'.",
                SourceLocation(1, 1),
            )
        return _PrimitiveConstructorRefV1(raw)

    @classmethod
    def _member_allowed(cls, member: _BoundMember) -> bool:
        receiver = member.receiver
        name = member.name
        if isinstance(receiver, str):
            return name in cls._STRING_MEMBERS
        if isinstance(receiver, list):
            return name in cls._LIST_MEMBERS
        if isinstance(receiver, dict):
            return name in cls._MAP_MEMBERS
        for receiver_type, members in cls._TYPED_MEMBER_ALLOWLIST.items():
            if isinstance(receiver, receiver_type):
                return name in members
        return False

    def member(self, receiver: Any, name: str, location: SourceLocation) -> Any:
        result = self._runtime._member(receiver, name, location)
        if isinstance(result, (FunctionDeclaration, ModuleFunction)):
            raise RuntimePrimitiveFacadeError(
                "KS5002",
                "Runtime primitive facade source AST callable üretemez.",
                location,
            )
        if isinstance(result, _BoundMember):
            if not self._member_allowed(result):
                raise RuntimePrimitiveFacadeError(
                    "KS5002",
                    f"MIR primitive member allowlist dışı: {type(result.receiver).__name__}.{result.name}.",
                    location,
                )
            return _PrimitiveMemberRefV1(result)
        if callable(result):
            raise RuntimePrimitiveFacadeError(
                "KS5002",
                "Runtime primitive facade raw host callable dışarı çıkaramaz.",
                location,
            )
        return result

    def invoke_primitive(
        self,
        callee: Any,
        arguments: list[Any],
        location: SourceLocation,
    ) -> Any:
        if isinstance(callee, (FunctionDeclaration, ModuleFunction)):
            raise RuntimePrimitiveFacadeError(
                "KS5002",
                "MIR primitive invoke source AST fonksiyonu çalıştıramaz.",
                location,
            )
        if isinstance(callee, str) and callee in self._BUILTIN_CALLS:
            return self._runtime._invoke(callee, arguments, location)
        if isinstance(callee, _PrimitiveConstructorRefV1):
            return self._runtime._invoke(callee.raw, arguments, location)
        if isinstance(callee, _PrimitiveMemberRefV1):
            if not self._member_allowed(callee.raw):
                raise RuntimePrimitiveFacadeError(
                    "KS5002",
                    "MIR primitive member ref allowlist doğrulamasını geçemedi.",
                    location,
                )
            return self._runtime._invoke_member(callee.raw, arguments)
        raise RuntimePrimitiveFacadeError(
            "KS5002",
            f"MIR primitive invoke allowlist dışı callee: {type(callee).__name__}.",
            location,
        )

    def is_runtime_error(self, value: Any) -> bool:
        return isinstance(value, KsError)

    def map_builder(self) -> MapBuilderV1:
        return MapBuilderV1.empty()

    def map_insert(
        self,
        builder: MapBuilderV1,
        key: Any,
        value: Any,
        location: SourceLocation,
    ) -> None:
        if not isinstance(builder, MapBuilderV1):
            raise RuntimePrimitiveFacadeError(
                "KS5002", "Geçersiz MIR Map builder.", location
            )
        builder.insert(
            key,
            value,
            contains_capability=self.contains_capability,
            runtime_type_name=self.runtime_type_name,
            location=location,
        )

    def map_finish(self, builder: MapBuilderV1, location: SourceLocation) -> dict[str, Any]:
        if not isinstance(builder, MapBuilderV1):
            raise RuntimePrimitiveFacadeError(
                "KS5002", "Geçersiz MIR Map builder.", location
            )
        return builder.finish()

    def struct_builder(self, type_name: str, location: SourceLocation) -> StructBuilderV1:
        declaration = self._runtime.structs.get(type_name)
        if declaration is None:
            raise RuntimePrimitiveFacadeError(
                "KS3101",
                f"MIR Struct declaration bulunamadı: '{type_name}'.",
                location,
            )
        return StructBuilderV1.empty(declaration)

    def struct_set(
        self,
        builder: StructBuilderV1,
        field: str,
        value: Any,
        location: SourceLocation,
    ) -> None:
        if not isinstance(builder, StructBuilderV1):
            raise RuntimePrimitiveFacadeError(
                "KS5002", "Geçersiz MIR Struct builder.", location
            )
        builder.set_field(
            field,
            value,
            contains_capability=self.contains_capability,
            matches_type=self.matches_type,
            runtime_type_name=self.runtime_type_name,
            location=location,
        )

    def struct_finish(self, builder: StructBuilderV1, location: SourceLocation):
        if not isinstance(builder, StructBuilderV1):
            raise RuntimePrimitiveFacadeError(
                "KS5002", "Geçersiz MIR Struct builder.", location
            )
        return builder.finish()

    def unwrap_fallible(self, value: Any) -> tuple[bool, Any]:
        return self._runtime._unwrap_fallible(value)

    def matches_type(self, value: Any, expected_names) -> bool:
        return self._runtime._runtime_matches_type(value, expected_names)

    def runtime_type_name(self, value: Any) -> str:
        return self._runtime._runtime_type_name(value)

    def contains_capability(self, value: Any) -> bool:
        return _contains_capability(value)

    def to_string(self, value: Any) -> str:
        return ks_to_string(value)
