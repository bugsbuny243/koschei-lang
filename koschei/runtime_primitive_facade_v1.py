"""Narrow runtime primitive ABI for sealed MIR execution.

The MIR executor may reuse existing runtime value/capability implementations, but
it must not acquire the reference interpreter's AST execution authority. This
facade exposes only primitive value operations needed by normalized MIR and
rejects source-language callable objects explicitly.
"""
from __future__ import annotations

from typing import Any

from .ast_nodes import FunctionDeclaration, Program, SourceLocation
from .container_runtime_v1 import MapBuilderV1, StructBuilderV1
from .interpreter import (
    Interpreter,
    KsError,
    KoscheiRuntimeError,
    ModuleFunction,
    _contains_capability,
    ks_to_string,
)


class RuntimePrimitiveFacadeError(KoscheiRuntimeError):
    pass


class RuntimePrimitiveFacadeV1:
    """AST-opaque primitive surface consumed by ``MirExecutorV1``."""

    __slots__ = ("_runtime",)

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
        return self._runtime.constructors.get(name)

    def member(self, receiver: Any, name: str, location: SourceLocation) -> Any:
        result = self._runtime._member(receiver, name, location)
        if isinstance(result, (FunctionDeclaration, ModuleFunction)):
            raise RuntimePrimitiveFacadeError(
                "KS5002",
                "Runtime primitive facade source AST callable üretemez.",
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
        return self._runtime._invoke(callee, arguments, location)

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
