"""Fail-closed execution of sealed Koschei MIR v4.

This executor consumes MIR blocks directly. Runtime value/capability primitives
are reached only through the AST-opaque RuntimePrimitiveFacadeV1. Unsupported
MIR migration boundaries fail closed instead of falling back to source AST.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ast_nodes import SourceLocation
from .interpreter import KsError, KsUnit, KoscheiRuntimeError, SystemCaps
from .mir import MIR_VERSION, MirGraph, MirIntegrityError
from .mir_container_staging_v1 import (
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
)
from .mir_extension_instructions_v4 import (
    MirMapContains,
    MirMapGet,
    MirMapKeys,
    MirMapSet,
    MirUnit,
    MirVariantIs,
    MirVariantPayload,
)
from .mir_ir import (
    MirAstFallback, MirBinary, MirBind, MirBranch, MirCall, MirConst,
    MirIterHasNext, MirIterInit, MirIterNext, MirJump, MirList, MirLoad,
    MirMember, MirReturn, MirStore, MirUnary, MirUnreachable,
)
from .mir_or_return_normalization_v1 import MirFallibleIsSuccess, MirFalliblePayload, MirInterpolate
from .mir_variant_runtime_v1 import MirVariantRuntimeError, variant_is_v1, variant_payload_v1
from .runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1
from .semantic import INT_MAX, INT_MIN
from .type_system import alternatives, render_type


class MirExecutionError(KoscheiRuntimeError):
    pass


def _runtime_names(type_node) -> tuple[str, ...]:
    return tuple(render_type(item) for item in alternatives(type_node))


@dataclass(frozen=True, slots=True)
class _MirFunctionRef:
    module_key: str
    function_name: str


@dataclass(frozen=True, slots=True)
class _MirModuleRef:
    module_key: str


@dataclass(slots=True)
class _MirIterator:
    values: list[Any]
    index: int = 0


class MirExecutorV1:
    MAX_CALL_DEPTH = 512

    def __init__(self, mir: MirGraph, argv: list[str] | None = None) -> None:
        if not isinstance(mir, MirGraph):
            raise MirIntegrityError("sealed MirGraph required for MIR execution")
        mir.assert_sealed()
        if mir.version != MIR_VERSION or mir.version != 4:
            raise MirIntegrityError(f"MIR executor v1 requires sealed MIR v4, got v{mir.version}")
        self.mir = mir
        self.argv = list(argv or [])
        root = mir.root_module
        self.primitives = RuntimePrimitiveFacadeV1(
            root.program, self.argv,
            namespaces=mir.namespaces(), imports=dict(root.imports), enums=mir.enums(),
            module_imports=mir.module_imports(), structs=mir.structs(),
        )
        self.depth = 0

    def execute_main(self) -> Any:
        root = self.mir.root_module
        main = next((item for item in root.functions if item.name == "main"), None)
        if main is None:
            raise MirExecutionError("KS3101", "'main' fonksiyonu MIR içinde bulunamadı.", SourceLocation(1, 1))
        if len(main.parameters) == 0:
            arguments: list[Any] = []
        elif len(main.parameters) == 1 and _runtime_names(main.parameters[0].type) == ("SystemCaps",):
            arguments = [SystemCaps()]
        else:
            raise MirExecutionError(
                "KS3401",
                "'main' MIR runtime'da sıfır parametre veya yalnızca bir SystemCaps parametresi almalıdır.",
                main.declaration.location,
            )
        return self._call(root.key, main.name, arguments)

    def _module_function(self, module_key: str, function_name: str):
        module = self.mir.module_of(module_key)
        function = next((item for item in module.functions if item.name == function_name), None)
        if function is None:
            raise MirExecutionError("KS3101", f"MIR fonksiyonu bulunamadı: {module.name}.{function_name}", SourceLocation(1, 1))
        return module, function

    def _call(self, module_key: str, function_name: str, arguments: list[Any]) -> Any:
        module, function = self._module_function(module_key, function_name)
        if len(arguments) != len(function.parameters):
            raise MirExecutionError("KS3101", f"'{function.name}' için {len(function.parameters)} argüman bekleniyor, {len(arguments)} verildi.", function.declaration.location)
        for parameter, value in zip(function.parameters, arguments):
            expected = _runtime_names(parameter.type)
            if not self.primitives.matches_type(value, expected):
                raise MirExecutionError("KS3401", f"'{function.name}' MIR çağrısında '{parameter.name}: {' or '.join(expected)}' sözleşmesi ihlal edildi.", function.declaration.location)
        if self.depth >= self.MAX_CALL_DEPTH:
            raise MirExecutionError("KS3105", f"Çağrı derinliği sınırı aşıldı ({self.MAX_CALL_DEPTH}).", function.declaration.location)

        bindings = {parameter.name: [value, False] for parameter, value in zip(function.parameters, arguments)}
        values: dict[int, Any] = {}
        blocks = {block.id: block for block in function.blocks}
        block_id = 0
        self.depth += 1
        try:
            while True:
                block = blocks.get(block_id)
                if block is None:
                    raise MirExecutionError("KS5002", f"MIR bilinmeyen bloğa geçti: {block_id}", function.declaration.location)
                for instruction in block.instructions:
                    self._execute_instruction(module.key, instruction, values, bindings)
                terminator = block.terminator
                if isinstance(terminator, MirReturn):
                    result = KsUnit if terminator.value is None else values[terminator.value]
                    expected_return = _runtime_names(function.return_type)
                    if not self.primitives.matches_type(result, expected_return):
                        raise MirExecutionError("KS3401", f"'{function.name}' MIR dönüş sözleşmesi {' or '.join(expected_return)} beklerken {self.primitives.runtime_type_name(result)} döndürdü.", function.declaration.location)
                    return result
                if isinstance(terminator, MirJump):
                    block_id = terminator.target
                    continue
                if isinstance(terminator, MirBranch):
                    condition = values[terminator.condition]
                    if isinstance(condition, KsError):
                        raise MirExecutionError(
                            "KS5002",
                            "MIR branch koşulu runtime Error değeri üretti; statement-result error continuation henüz canonical MIR içinde normalize edilmedi.",
                            function.declaration.location,
                        )
                    block_id = terminator.then_block if bool(condition) else terminator.else_block
                    continue
                if isinstance(terminator, MirUnreachable):
                    raise MirExecutionError("KS5002", f"MIR unreachable bloğa ulaştı: {terminator.reason}", function.declaration.location)
                raise MirExecutionError("KS5002", "Bilinmeyen MIR terminator.", function.declaration.location)
        finally:
            self.depth -= 1

    def _load_name(self, module_key: str, name: str, bindings: dict[str, list[Any]], location):
        if name in bindings:
            return bindings[name][0]
        module = self.mir.module_of(module_key)
        if any(function.name == name for function in module.functions):
            return _MirFunctionRef(module_key, name)
        constructor = self.primitives.constructor(name)
        if constructor is not None:
            return constructor
        if name in {"print", "println", "Error"}:
            return name
        imported_key = module.imports.get(name)
        if imported_key is not None:
            return _MirModuleRef(imported_key)
        raise MirExecutionError("KS3101", f"Tanımsız MIR isim: '{name}'.", location)

    def _execute_instruction(self, module_key: str, instruction, values: dict[int, Any], bindings: dict[str, list[Any]]) -> None:
        if isinstance(instruction, MirAstFallback):
            raise MirExecutionError("KS5002", f"MIR executor AST fallback çalıştırmaz: {instruction.node_kind}", instruction.location)
        if isinstance(instruction, MirUnit):
            values[instruction.target] = KsUnit
            return
        if isinstance(instruction, MirConst):
            value = instruction.value
            if type(value) is int and not INT_MIN <= value <= INT_MAX:
                value = KsError(f"KS3501: Int literal 64-bit aralığı aştı: {value}")
            values[instruction.target] = value
            return
        if isinstance(instruction, MirLoad):
            values[instruction.target] = self._load_name(module_key, instruction.name, bindings, instruction.location)
            return
        if isinstance(instruction, MirBind):
            bindings[instruction.name] = [values[instruction.source], instruction.is_mutable]
            return
        if isinstance(instruction, MirStore):
            cell = bindings.get(instruction.name)
            if cell is None:
                raise MirExecutionError("KS3101", f"Tanımsız MIR binding: '{instruction.name}'.", instruction.location)
            if not cell[1]:
                raise MirExecutionError("KS3201", f"'{instruction.name}' immutable bir MIR binding'dir.", instruction.location)
            cell[0] = values[instruction.source]
            return
        if isinstance(instruction, MirUnary):
            operand = values[instruction.operand]
            if isinstance(operand, KsError):
                values[instruction.target] = operand
            elif instruction.operator == "!":
                values[instruction.target] = not bool(operand)
            elif instruction.operator == "-":
                if type(operand) is int and operand == INT_MIN:
                    values[instruction.target] = KsError("KS3501: Int taşması: 'unary -'")
                else:
                    values[instruction.target] = -operand
            else:
                raise MirExecutionError("KS5002", f"Bilinmeyen MIR unary operator: {instruction.operator}", instruction.location)
            return
        if isinstance(instruction, MirBinary):
            values[instruction.target] = self._binary(instruction, values)
            return
        if isinstance(instruction, MirList):
            items = [values[item] for item in instruction.items]
            if any(self.primitives.contains_capability(item) for item in items):
                raise MirExecutionError("KS3401", "Capability taşıyan değer MIR List içine konamaz.", instruction.location)
            values[instruction.target] = items
            return
        if isinstance(instruction, MirInterpolate):
            values[instruction.target] = "".join(self.primitives.to_string(values[item]) for item in instruction.items)
            return
        if isinstance(instruction, MirIsRuntimeError):
            values[instruction.target] = self.primitives.is_runtime_error(values[instruction.source])
            return
        if isinstance(instruction, MirVariantIs):
            try:
                values[instruction.target] = variant_is_v1(
                    values[instruction.source], instruction.variant
                )
            except MirVariantRuntimeError as error:
                raise MirExecutionError(
                    "KS5002",
                    f"Canonical MIR variant comparison failed closed: {error}",
                    instruction.location,
                ) from error
            return
        if isinstance(instruction, MirVariantPayload):
            try:
                values[instruction.target] = variant_payload_v1(
                    values[instruction.source], instruction.variant
                )
            except MirVariantRuntimeError as error:
                raise MirExecutionError(
                    "KS5002",
                    f"Canonical MIR variant payload failed closed: {error}",
                    instruction.location,
                ) from error
            return
        if isinstance(instruction, MirMapNew):
            values[instruction.target] = self.primitives.map_builder()
            return
        if isinstance(instruction, MirMapInsert):
            key, value = instruction.arguments
            self.primitives.map_insert(values[instruction.object], values[key], values[value], instruction.location)
            return
        if isinstance(instruction, MirMapFinish):
            values[instruction.target] = self.primitives.map_finish(values[instruction.source], instruction.location)
            return
        if isinstance(instruction, MirMapGet):
            values[instruction.target] = self.primitives.map_get(
                values[instruction.object],
                values[instruction.key],
                instruction.location,
            )
            return
        if isinstance(instruction, MirMapSet):
            values[instruction.target] = self.primitives.map_set(
                values[instruction.object],
                values[instruction.key],
                values[instruction.value],
                instruction.location,
            )
            return
        if isinstance(instruction, MirMapKeys):
            values[instruction.target] = self.primitives.map_keys(
                values[instruction.object],
                instruction.location,
            )
            return
        if isinstance(instruction, MirMapContains):
            values[instruction.target] = self.primitives.map_contains(
                values[instruction.object],
                values[instruction.key],
                instruction.location,
            )
            return
        if isinstance(instruction, MirStructNew):
            values[instruction.target] = self.primitives.struct_builder(instruction.type_name, instruction.location)
            return
        if isinstance(instruction, MirStructSet):
            self.primitives.struct_set(values[instruction.object], instruction.field, values[instruction.source], instruction.location)
            return
        if isinstance(instruction, MirStructFinish):
            values[instruction.target] = self.primitives.struct_finish(values[instruction.source], instruction.location)
            return
        if isinstance(instruction, MirIterInit):
            iterable = values[instruction.iterable]
            if not isinstance(iterable, list):
                raise MirExecutionError("KS3101", "MIR iterator yalnızca List üzerinde kurulabilir.", instruction.location)
            values[instruction.target] = _MirIterator(iterable)
            return
        if isinstance(instruction, MirIterHasNext):
            iterator = values[instruction.iterator]
            values[instruction.target] = iterator.index < len(iterator.values)
            return
        if isinstance(instruction, MirIterNext):
            iterator = values[instruction.iterator]
            if iterator.index >= len(iterator.values):
                raise MirExecutionError("KS5002", "MIR iterator sınır dışı next.", instruction.location)
            values[instruction.target] = iterator.values[iterator.index]
            iterator.index += 1
            return
        if isinstance(instruction, MirMember):
            receiver = values[instruction.object]
            if isinstance(receiver, _MirModuleRef):
                values[instruction.target] = _MirFunctionRef(receiver.module_key, instruction.member)
            else:
                values[instruction.target] = self.primitives.member(receiver, instruction.member, instruction.location)
            return
        if isinstance(instruction, MirCall):
            callee = values[instruction.callee]
            arguments = [values[item] for item in instruction.arguments]
            result = self._call(callee.module_key, callee.function_name, arguments) if isinstance(callee, _MirFunctionRef) else self.primitives.invoke_primitive(callee, arguments, instruction.location)
            values[instruction.target] = result
            return
        if isinstance(instruction, MirFallibleIsSuccess):
            success, _ = self.primitives.unwrap_fallible(values[instruction.source])
            values[instruction.target] = success
            return
        if isinstance(instruction, MirFalliblePayload):
            success, payload = self.primitives.unwrap_fallible(values[instruction.source])
            if not success:
                raise MirExecutionError("KS5002", "MirFalliblePayload yalnızca kanıtlanmış success yolunda çalışabilir.", instruction.location)
            values[instruction.target] = payload
            return
        raise MirExecutionError("KS5002", f"Desteklenmeyen MIR instruction: {type(instruction).__name__}", instruction.location)

    def _binary(self, instruction: MirBinary, values: dict[int, Any]) -> Any:
        left = values[instruction.left]
        if isinstance(left, KsError):
            return left
        op = instruction.operator
        if op == "&&":
            if not bool(left):
                return False
            right = values[instruction.right]
            return right if isinstance(right, KsError) else bool(right)
        if op == "||":
            if bool(left):
                return True
            right = values[instruction.right]
            return right if isinstance(right, KsError) else bool(right)
        right = values[instruction.right]
        if isinstance(right, KsError):
            return right
        if op in {"+", "-", "*"} and type(left) is int and type(right) is int:
            result = left + right if op == "+" else left - right if op == "-" else left * right
            if not INT_MIN <= result <= INT_MAX:
                return KsError(f"KS3501: Int taşması: '{op}'")
            return result
        if op == "+": return left + right
        if op == "-": return left - right
        if op == "*": return left * right
        if op == "/": return KsError("Sıfıra bölme") if right == 0 else left / right
        if op == "==": return left == right
        if op == "!=": return left != right
        if op == "<": return left < right
        if op == "<=": return left <= right
        if op == ">": return left > right
        if op == ">=": return left >= right
        raise MirExecutionError("KS5002", f"Bilinmeyen MIR binary operator: {op}", instruction.location)


def execute_mir_v1(mir: MirGraph, argv: list[str] | None = None) -> Any:
    return MirExecutorV1(mir, argv).execute_main()
