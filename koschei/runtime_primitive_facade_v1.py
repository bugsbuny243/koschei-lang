"""Narrow runtime primitive ABI for sealed MIR execution.

The MIR executor may reuse existing runtime value/capability implementations, but
it must not acquire the reference interpreter's AST execution authority. This
facade exposes only primitive value operations needed by normalized MIR and
rejects source-language callable objects explicitly.
"""
from __future__ import annotations

from typing import Any

from .ast_nodes import FunctionDeclaration, Program, SourceLocation
from .interpreter import (
    Interpreter,
    KoscheiRuntimeError,
    ModuleFunction,
    _contains_capability,
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
        # Interpreter is retained only as an implementation container for the
        # already-defined runtime value/capability primitive semantics. No AST
        # execute/evaluate/call entrypoint is exposed through this facade.
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

    def unwrap_fallible(self, value: Any) -> tuple[bool, Any]:
        return self._runtime._unwrap_fallible(value)

    def matches_type(self, value: Any, expected_names) -> bool:
        return self._runtime._runtime_matches_type(value, expected_names)

    def runtime_type_name(self, value: Any) -> str:
        return self._runtime._runtime_type_name(value)

    def contains_capability(self, value: Any) -> bool:
        return _contains_capability(value)
