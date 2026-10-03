"""Budgeted canonical MIR execution for the public ``ks run`` boundary.

The public budget router used to fail closed whenever sealed variant facts were
present but the stricter native MIR runtime could not admit the whole graph.
That was safe, but it also rejected programs the canonical AST-opaque MIR v4
executor already knows how to execute (notably generic Option/enum programs).

This module keeps the fail-closed authority rule while adding the missing
resource-budget bridge: canonical MIR may fall back only to ``MirExecutorV1``,
never to the checked-AST compatibility interpreter.
"""
from __future__ import annotations

import sys
from typing import Any

from . import interpreter
from .interpreter import KsError, KsUnit
from .mir_executor_v1 import MirExecutionError, MirExecutorV1, _runtime_names
from .mir_ir import MirBranch, MirJump, MirReturn, MirUnreachable
from .mir_instruction_registry_v4 import require_mir_v4_graph_registry
from .runtime_boot_v1 import require_runtime_ready


class BudgetedCanonicalMirExecutorV1(MirExecutorV1):
    """Sealed MIR v4 executor with explicit step and call-depth accounting."""

    def __init__(self, mir, argv: list[str] | None, *, budget: Any) -> None:
        super().__init__(mir, argv)
        self.runtime_budget = budget

    def _call(self, module_key: str, function_name: str, arguments: list[Any]) -> Any:
        module, function = self._module_function(module_key, function_name)
        if len(arguments) != len(function.parameters):
            raise MirExecutionError(
                "KS3101",
                f"'{function.name}' için {len(function.parameters)} argüman bekleniyor, {len(arguments)} verildi.",
                function.declaration.location,
            )

        type_parameters = frozenset(
            getattr(function.declaration, "type_parameters", ())
        )
        type_bindings: dict[str, str] | None = {} if type_parameters else None
        for parameter, value in zip(function.parameters, arguments):
            expected = _runtime_names(parameter.type)
            if not self.primitives.matches_type(
                value,
                expected,
                type_parameters=type_parameters,
                type_bindings=type_bindings,
            ):
                if type_parameters:
                    raise MirExecutionError(
                        "KS3106",
                        f"'{function.name}' MIR generic çağrısında "
                        f"'{parameter.name}: {' or '.join(expected)}' için çelişkili "
                        "runtime tip kanıtı bulundu; bu bir capability ihlali değildir.",
                        function.declaration.location,
                    )
                raise MirExecutionError(
                    "KS3401",
                    f"'{function.name}' MIR çağrısında '{parameter.name}: {' or '.join(expected)}' sözleşmesi ihlal edildi.",
                    function.declaration.location,
                )

        if self.depth >= self.MAX_CALL_DEPTH:
            raise MirExecutionError(
                "KS3105",
                f"Çağrı derinliği sınırı aşıldı ({self.MAX_CALL_DEPTH}).",
                function.declaration.location,
            )

        self.runtime_budget.enter_call(function.declaration.location)
        bindings = {
            parameter.name: [value, False]
            for parameter, value in zip(function.parameters, arguments)
        }
        values: dict[int, Any] = {}
        blocks = {block.id: block for block in function.blocks}
        block_id = 0
        self.depth += 1
        try:
            while True:
                block = blocks.get(block_id)
                if block is None:
                    raise MirExecutionError(
                        "KS5002",
                        f"MIR bilinmeyen bloğa geçti: {block_id}",
                        function.declaration.location,
                    )

                # Charge every instruction and every block transition.  The
                # latter prevents an empty-block cycle from escaping the budget.
                for instruction in block.instructions:
                    self.runtime_budget.consume_step(instruction.location)
                    self._execute_instruction(
                        module.key, instruction, values, bindings
                    )
                terminator = block.terminator
                self.runtime_budget.consume_step(
                    getattr(terminator, "location", function.declaration.location)
                )

                if isinstance(terminator, MirReturn):
                    result = KsUnit if terminator.value is None else values[terminator.value]
                    expected_return = _runtime_names(function.return_type)
                    if not self.primitives.matches_type(
                        result,
                        expected_return,
                        type_parameters=type_parameters,
                        type_bindings=type_bindings,
                    ):
                        if type_parameters:
                            raise MirExecutionError(
                                "KS3106",
                                f"'{function.name}' MIR generic dönüş sözleşmesi "
                                f"{' or '.join(expected_return)} ile runtime sonucu "
                                "çelişiyor; bu bir capability ihlali değildir.",
                                function.declaration.location,
                            )
                        raise MirExecutionError(
                            "KS3401",
                            f"'{function.name}' MIR dönüş sözleşmesi {' or '.join(expected_return)} beklerken "
                            f"{self.primitives.runtime_type_name(result)} döndürdü.",
                            function.declaration.location,
                        )
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
                    block_id = (
                        terminator.then_block
                        if bool(condition)
                        else terminator.else_block
                    )
                    continue
                if isinstance(terminator, MirUnreachable):
                    raise MirExecutionError(
                        "KS5002",
                        f"MIR unreachable bloğa ulaştı: {terminator.reason}",
                        function.declaration.location,
                    )
                raise MirExecutionError(
                    "KS5002", "Bilinmeyen MIR terminator.", function.declaration.location
                )
        finally:
            self.depth -= 1
            self.runtime_budget.leave_call()


def _run_budgeted_canonical_mir(mir_graph, argv, budget) -> int:
    require_runtime_ready(interpreter)
    mir_graph.assert_sealed()
    require_mir_v4_graph_registry(mir_graph)
    result = BudgetedCanonicalMirExecutorV1(
        mir_graph, list(argv or []), budget=budget
    ).execute_main()
    if isinstance(result, interpreter.KsError):
        print(f"KOSCHEI RUNTIME ERROR: {result.message}", file=sys.stderr)
        return 1
    return 0


def install_canonical_mir_budget_runtime_v1() -> None:
    """Route compiler-owned MIR facts to the budgeted canonical executor."""

    from . import runtime_budget

    current = runtime_budget.run_mir_with_budget
    if getattr(current, "_koschei_canonical_mir_budget_v1", False):
        return

    def run_mir_with_budget(
        mir_graph,
        argv: list[str] | None = None,
        *,
        max_steps: int = runtime_budget.DEFAULT_MAX_STEPS,
        max_call_depth: int = runtime_budget.HARD_MAX_CALL_DEPTH,
    ) -> int:
        mir_graph.assert_sealed()
        mode = runtime_budget.runtime_execution_mode(mir_graph)
        if (
            mode != "mir_native_v1"
            and runtime_budget._requires_canonical_mir_runtime_v1(mir_graph)
        ):
            budget = runtime_budget.RuntimeBudget(
                max_steps=max_steps,
                max_call_depth=max_call_depth,
            )
            return _run_budgeted_canonical_mir(mir_graph, argv, budget)
        return current(
            mir_graph,
            argv,
            max_steps=max_steps,
            max_call_depth=max_call_depth,
        )

    run_mir_with_budget._koschei_canonical_mir_budget_v1 = True
    runtime_budget.run_mir_with_budget = run_mir_with_budget


__all__ = [
    "BudgetedCanonicalMirExecutorV1",
    "install_canonical_mir_budget_runtime_v1",
]
