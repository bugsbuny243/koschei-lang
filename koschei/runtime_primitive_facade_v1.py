"""Narrow runtime primitive ABI for sealed MIR execution.

The MIR executor may reuse existing runtime value/capability implementations, but
it must not acquire the reference interpreter's AST execution authority or carry
raw interpreter callable objects across the MIR/runtime boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .ast_nodes import FunctionDeclaration, Program, SourceLocation
from .container_runtime_v1 import (
    MapBuilderV1,
    StructBuilderV1,
    map_contains_v1,
    map_get_v1,
    map_keys_v1,
    map_set_v1,
)
from . import interpreter as runtime_module
from .runtime_capability_registry_v1 import (
    canonical_runtime_registry,
    capability_type_name_for_value,
)
from .interpreter import (
    DiskCaps,
    DiskReadCaps,
    DiskRoot,
    EnvCaps,
    EnvRoot,
    EnumValue,
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
class KoscheiFunctionRefV1:
    """Opaque sealed-MIR function identity; never source AST authority."""

    module_key: str
    function_name: str


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

    __slots__ = ("_runtime", "_invoke_function")

    _BUILTIN_CALLS = frozenset({
        "print",
        "println",
        "Error",
        "bounded_queue",
        "queue_try_send",
        "queue_try_recv",
        "queue_len",
        "queue_capacity",
        "parallel_map",
        "decimal",
        "decimal_add",
        "decimal_sub",
        "decimal_cmp",
        "decimal_text",
        "task_scope",
        "task_spawn",
        "task_join_all",
        "task_pending",
        "task_capacity",
        "task_closed",
        "task_cancel",
        "task_cancel_all",
    })
    _STRING_MEMBERS = frozenset(
        {"length", "to_int", "to_float", "contains", "trim", "split", "join"}
    )
    _LIST_MEMBERS = frozenset({
        "length", "get", "push", "contains", "sort", "filter",
        "take", "find", "first_difference", "sum", "min", "max",
        "unique", "flatten", "chunks", "map", "any", "partition", "scan",
    })
    _MAP_MEMBERS = frozenset({
        "get", "set", "keys", "contains", "keys_sorted_by_value", "merge", "add",
    })
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
        invoke_function: Callable[[KoscheiFunctionRefV1, list[Any]], Any],
    ) -> None:
        self._invoke_function = invoke_function
        self._runtime = Interpreter(
            program,
            argv,
            namespaces=namespaces,
            imports=imports,
            enums=enums,
            module_imports=module_imports,
            structs=structs,
        )

    @classmethod
    def builtin(cls, name: str) -> str | None:
        return name if name in cls._BUILTIN_CALLS else None

    @staticmethod
    def function_ref(module_key: str, function_name: str) -> KoscheiFunctionRefV1:
        return KoscheiFunctionRefV1(module_key, function_name)

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

        capability_type = capability_type_name_for_value(runtime_module, receiver)
        if capability_type is not None and capability_type != "SystemCaps":
            spec = canonical_runtime_registry().capabilities.get(capability_type)
            return spec is not None and name in spec.methods

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

    def _require_callback(
        self,
        value: Any,
        *,
        method: str,
        location: SourceLocation,
    ) -> KoscheiFunctionRefV1 | KsError:
        if isinstance(value, KoscheiFunctionRefV1):
            return value
        return KsError(
            f"List.{method}() yerel, adlandırılmış Koschei fonksiyonu bekler"
        )

    def _invoke_list_callback_member(
        self,
        member: _PrimitiveMemberRefV1,
        arguments: list[Any],
    ) -> Any:
        receiver = member.raw.receiver
        name = member.raw.name
        location = member.raw.location
        if not isinstance(receiver, list):
            raise RuntimePrimitiveFacadeError(
                "KS5002", "List callback transition received non-List receiver.", location
            )

        if name in {"filter", "find", "map", "any", "partition"}:
            self._runtime._require_arity(name, arguments, 1, location)
            callback = self._require_callback(arguments[0], method=name, location=location)
            if isinstance(callback, KsError):
                return callback
            if _contains_capability(receiver):
                raise RuntimePrimitiveFacadeError(
                    "KS3401",
                    f"Capability taşıyan List üzerinde {name}() çalıştırılamaz.",
                    location,
                )

            if name == "filter":
                out: list[Any] = []
                for item in receiver:
                    decision = self._invoke_function(callback, [item])
                    if isinstance(decision, KsError):
                        return decision
                    if not isinstance(decision, bool):
                        return KsError("List.filter() predicate'i Bool döndürmelidir")
                    if decision:
                        out.append(item)
                return out

            if name == "find":
                for item in receiver:
                    decision = self._invoke_function(callback, [item])
                    if isinstance(decision, KsError):
                        return decision
                    if not isinstance(decision, bool):
                        return KsError("List.find() predicate'i Bool döndürmelidir")
                    if decision:
                        return EnumValue("Option", "Some", item)
                return EnumValue("Option", "None")

            if name == "map":
                out: list[Any] = []
                for item in receiver:
                    mapped = self._invoke_function(callback, [item])
                    if isinstance(mapped, KsError):
                        return mapped
                    if _contains_capability(mapped):
                        raise RuntimePrimitiveFacadeError(
                            "KS3401",
                            "List.map() callback'i capability döndüremez.",
                            location,
                        )
                    out.append(mapped)
                return out

            if name == "any":
                for item in receiver:
                    decision = self._invoke_function(callback, [item])
                    if isinstance(decision, KsError):
                        return decision
                    if not isinstance(decision, bool):
                        return KsError("List.any() predicate'i Bool döndürmelidir")
                    if decision:
                        return True
                return False

            matching: list[Any] = []
            rejected: list[Any] = []
            for item in receiver:
                decision = self._invoke_function(callback, [item])
                if isinstance(decision, KsError):
                    return decision
                if not isinstance(decision, bool):
                    return KsError("List.partition() predicate'i Bool döndürmelidir")
                (matching if decision else rejected).append(item)
            return [matching, rejected]

        if name == "scan":
            self._runtime._require_arity(name, arguments, 2, location)
            initial, reducer_value = arguments
            reducer = self._require_callback(reducer_value, method=name, location=location)
            if isinstance(reducer, KsError):
                return reducer
            if _contains_capability(receiver) or _contains_capability(initial):
                raise RuntimePrimitiveFacadeError(
                    "KS3401",
                    "Capability taşıyan List veya başlangıç değeri üzerinde scan() çalıştırılamaz.",
                    location,
                )
            accumulator = initial
            out: list[Any] = []
            for item in receiver:
                accumulator = self._invoke_function(reducer, [accumulator, item])
                if isinstance(accumulator, KsError):
                    return accumulator
                if _contains_capability(accumulator):
                    raise RuntimePrimitiveFacadeError(
                        "KS3401",
                        "List.scan() reducer'ı capability döndüremez.",
                        location,
                    )
                out.append(accumulator)
            return out

        raise RuntimePrimitiveFacadeError(
            "KS5002", f"Unsupported List callback transition: {name}.", location
        )

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
            if (
                isinstance(callee.raw.receiver, list)
                and callee.raw.name in {"filter", "find", "map", "any", "partition", "scan"}
            ):
                return self._invoke_list_callback_member(callee, arguments)
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
        return builder.finish(location)

    def map_get(self, value: Any, key: Any, location: SourceLocation) -> Any:
        return map_get_v1(value, key, location)

    def map_set(
        self,
        value: Any,
        key: Any,
        item: Any,
        location: SourceLocation,
    ) -> dict[str, Any]:
        return map_set_v1(
            value,
            key,
            item,
            contains_capability=self.contains_capability,
            location=location,
        )

    def map_keys(self, value: Any, location: SourceLocation) -> list[str]:
        return map_keys_v1(value, location)

    def map_contains(self, value: Any, key: Any, location: SourceLocation) -> bool:
        return map_contains_v1(value, key, location)

    def struct_builder(
        self,
        type_name: str,
        required_fields: tuple[str, ...],
        location: SourceLocation,
    ) -> StructBuilderV1:
        declaration = self._runtime.structs.get(type_name)
        if declaration is None:
            raise RuntimePrimitiveFacadeError(
                "KS3101",
                f"MIR Struct declaration bulunamadı: '{type_name}'.",
                location,
            )
        return StructBuilderV1.empty(declaration, required_fields, location)

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
        return builder.finish(location)

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
