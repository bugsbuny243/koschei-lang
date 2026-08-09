"""Fail-closed runtime resource budgets for Koschei V5.

Normalized graphs that the direct MIR runtime can execute are now routed through
that backend. Graphs containing not-yet-normalized language constructs remain on
the checked AST compatibility interpreter. Both paths preserve explicit step and
call-depth budgets; the selected mode is deterministic and inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any, Literal

from .ast_nodes import SourceLocation
from .diagnostics import CATALOG, ENGLISH_CATALOG, Diagnostic
from .interpreter import Interpreter, KoscheiRuntimeError, KsError
from .mir_native_runtime import (
    MirNativeCallDepthExceeded,
    MirNativeProgramError,
    MirNativeRuntimeError,
    MirNativeStepBudgetExceeded,
    inspect_native_mir_support,
    run_mir_native,
)

DEFAULT_MAX_STEPS = 1_000_000
HARD_MAX_CALL_DEPTH = Interpreter.MAX_CALL_DEPTH
RuntimeExecutionMode = Literal["mir_native_v1", "ast_compat_v1"]


@dataclass(slots=True)
class RuntimeBudget:
    """Mutable execution meter shared by every call in one interpreter run."""

    max_steps: int = DEFAULT_MAX_STEPS
    max_call_depth: int = HARD_MAX_CALL_DEPTH
    steps: int = 0
    call_depth: int = 0

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        if self.max_call_depth <= 0:
            raise ValueError("max_call_depth must be a positive integer")
        if self.max_call_depth > HARD_MAX_CALL_DEPTH:
            raise ValueError(
                f"max_call_depth cannot exceed the hard safety ceiling "
                f"({HARD_MAX_CALL_DEPTH})"
            )

    def consume_step(self, location: SourceLocation) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise KoscheiRuntimeError(
                "KS3601",
                f"Çalıştırma adım bütçesi tükendi ({self.max_steps}); "
                "sonsuz döngü veya beklenmeyen ölçüde pahalı hesap olabilir.",
                location,
            )

    def enter_call(self, location: SourceLocation) -> None:
        if self.call_depth >= self.max_call_depth:
            raise KoscheiRuntimeError(
                "KS3602",
                f"Kullanıcı çağrı derinliği bütçesi aşıldı "
                f"({self.max_call_depth}); özyineleme durmuyor olabilir.",
                location,
            )
        self.call_depth += 1

    def leave_call(self) -> None:
        self.call_depth -= 1


class BudgetedInterpreter(Interpreter):
    """AST compatibility interpreter with statement/expression metering."""

    def __init__(self, *args: Any, budget: RuntimeBudget, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.runtime_budget = budget

    def _execute_statement(self, statement):
        self.runtime_budget.consume_step(statement.location)
        return super()._execute_statement(statement)

    def _evaluate(self, expression):
        self.runtime_budget.consume_step(expression.location)
        return super()._evaluate(expression)

    def _call_function(
        self,
        function,
        arguments,
        namespace=None,
        imports=None,
    ):
        self.runtime_budget.enter_call(function.location)
        try:
            return super()._call_function(
                function,
                arguments,
                namespace=namespace,
                imports=imports,
            )
        finally:
            self.runtime_budget.leave_call()


def runtime_execution_mode(mir_graph) -> RuntimeExecutionMode:
    """Report which checked runtime lane will execute this sealed graph."""

    return (
        "mir_native_v1"
        if inspect_native_mir_support(mir_graph).supported
        else "ast_compat_v1"
    )


def run_mir_with_budget(
    mir_graph,
    argv: list[str] | None = None,
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_call_depth: int = HARD_MAX_CALL_DEPTH,
) -> int:
    """Execute a sealed MIR graph under explicit resource budgets."""

    mir_graph.assert_sealed()
    budget = RuntimeBudget(max_steps=max_steps, max_call_depth=max_call_depth)
    if runtime_execution_mode(mir_graph) == "mir_native_v1":
        try:
            return run_mir_native(
                mir_graph,
                max_steps=budget.max_steps,
                max_call_depth=budget.max_call_depth,
            )
        except MirNativeStepBudgetExceeded as exc:
            raise KoscheiRuntimeError(
                "KS3601",
                f"Çalıştırma adım bütçesi tükendi ({budget.max_steps}); "
                "sonsuz döngü veya beklenmeyen ölçüde pahalı hesap olabilir.",
                SourceLocation(1, 1),
            ) from exc
        except MirNativeCallDepthExceeded as exc:
            raise KoscheiRuntimeError(
                "KS3602",
                f"Kullanıcı çağrı derinliği bütçesi aşıldı "
                f"({budget.max_call_depth}); özyineleme durmuyor olabilir.",
                SourceLocation(1, 1),
            ) from exc
        except MirNativeProgramError as exc:
            print(f"KOSCHEI RUNTIME ERROR: {exc}", file=sys.stderr)
            return 1
        except MirNativeRuntimeError as exc:
            raise KoscheiRuntimeError(
                "KS3401",
                f"Native MIR runtime sözleşmesi ihlal edildi: {exc}",
                SourceLocation(1, 1),
            ) from exc

    root = mir_graph.root_module
    result = BudgetedInterpreter(
        root.program,
        list(argv or []),
        namespaces=mir_graph.namespaces(),
        imports=dict(root.imports),
        enums=mir_graph.enums(),
        module_imports=mir_graph.module_imports(),
        structs=mir_graph.structs(),
        budget=budget,
    ).execute_main()
    if isinstance(result, KsError):
        print(f"KOSCHEI RUNTIME ERROR: {result.message}", file=sys.stderr)
        return 1
    return 0


def positive_step_budget(text: str) -> int:
    return _positive_integer(text, "--max-steps")


def bounded_call_depth(text: str) -> int:
    value = _positive_integer(text, "--max-call-depth")
    if value > HARD_MAX_CALL_DEPTH:
        raise ValueError(f"--max-call-depth cannot exceed {HARD_MAX_CALL_DEPTH}")
    return value


def _positive_integer(text: str, option: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise ValueError(f"{option} expects a positive integer") from error
    if value <= 0:
        raise ValueError(f"{option} expects a positive integer")
    return value


def _register_diagnostics() -> None:
    CATALOG.setdefault(
        "KS3601",
        Diagnostic(
            "KS3601",
            "Çalıştırma adım bütçesi tükendi",
            "Yorumlayıcı, izin verilen statement/expression adımı sayısını aştı.",
            "Sınırsız döngüler ve saldırgan girdiler CPU'yu sonsuza kadar meşgul "
            "edebilir. Koschei çalışmayı host sürecini kilitlemeden durdurur.",
            "Döngünün ilerlediğini doğrulayın veya bilinçli uzun işler için "
            "--max-steps değerini yükseltin.",
            "ks run app.ks --max-steps 2000000",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3601",
        Diagnostic(
            "KS3601",
            "Execution step budget exhausted",
            "The interpreter exceeded the allowed statement/expression steps.",
            "Unbounded loops and adversarial inputs can monopolize CPU. Koschei "
            "stops the program instead of hanging the host process.",
            "Verify loop progress or raise --max-steps for an intentionally long run.",
            "ks run app.ks --max-steps 2000000",
        ),
    )
    CATALOG.setdefault(
        "KS3602",
        Diagnostic(
            "KS3602",
            "Kullanıcı çağrı derinliği bütçesi aşıldı",
            "Program, çalıştırma için seçilen eşzamanlı Koschei çağrı sınırını aştı.",
            "Kontrolsüz özyineleme host stack'ini tüketebilir. Kullanıcı bütçesi, "
            "dilin 512 çerçevelik sert tavanından daha erken ve öngörülebilir durur.",
            "Bir durma koşulu ekleyin, iterasyon kullanın veya güvenli olduğu "
            "kanıtlanan iş için --max-call-depth değerini yükseltin.",
            "ks run app.ks --max-call-depth 128",
        ),
    )
    ENGLISH_CATALOG.setdefault(
        "KS3602",
        Diagnostic(
            "KS3602",
            "User call-depth budget exceeded",
            "The program exceeded the selected simultaneous Koschei call limit.",
            "Uncontrolled recursion can exhaust the host stack. The user budget "
            "fails earlier than the language's hard 512-frame ceiling.",
            "Add a base case, use iteration, or raise --max-call-depth for a proven-safe run.",
            "ks run app.ks --max-call-depth 128",
        ),
    )


_register_diagnostics()
