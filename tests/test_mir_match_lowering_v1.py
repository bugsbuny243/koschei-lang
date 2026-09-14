from __future__ import annotations

from dataclasses import dataclass

import pytest

from koschei.ast_nodes import Identifier, Literal, MatchArm, MatchExpression, Program, SourceLocation
from koschei.mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from koschei.mir_ir import MirBind, MirBranch, MirConst, MirJump, MirLoad, MirUnreachable
from koschei.mir_match_lowering_v1 import lower_match_expression_v1
from koschei.mir_match_plan_v1 import MirMatchPlanError
from koschei.type_system import INT, BOOL, generic
from koschei.typed_hir import TypedHIRChecker, TypedHIRReport


@dataclass
class _Block:
    id: int
    instructions: list
    terminator: object | None = None


class _FakeLowerer:
    def __init__(self, typed_report: TypedHIRReport, expression: MatchExpression) -> None:
        self.typed_report = typed_report
        self.expression = expression
        self.blocks = {0: _Block(0, [])}
        self.current = 0
        self.next_block = 1
        self.next_value = 0
        self.next_binding = 0
        self.scopes = [{"choice": "choice"}]
        self.used_binding_names = {"choice"}
        self.scrutinee_evaluations = 0

    def _new_value(self):
        value = self.next_value
        self.next_value += 1
        return value

    def _new_block(self):
        block = self.next_block
        self.next_block += 1
        self.blocks[block] = _Block(block, [])
        return block

    def _emit(self, instruction):
        assert self.blocks[self.current].terminator is None
        self.blocks[self.current].instructions.append(instruction)

    def _terminate(self, terminator):
        assert self.blocks[self.current].terminator is None
        self.blocks[self.current].terminator = terminator

    def _new_internal_binding_name(self, purpose: str):
        name = f"$mir_{purpose}_{self.next_binding}"
        self.next_binding += 1
        self.used_binding_names.add(name)
        return name

    def _new_binding_name(self, source_name: str):
        name = source_name
        if name in self.used_binding_names:
            name = f"{source_name}$mir{self.next_binding}"
            self.next_binding += 1
        self.used_binding_names.add(name)
        self.scopes[-1][source_name] = name
        return name

    def _resolve_binding_name(self, source_name: str):
        for scope in reversed(self.scopes):
            if source_name in scope:
                return scope[source_name]
        return source_name

    def _type_of(self, expression):
        for item in self.typed_report.expressions:
            if item.expression is expression:
                return item.type
        return INT

    def _lower_expression(self, expression):
        if expression is self.expression.value:
            self.scrutinee_evaluations += 1
        target = self._new_value()
        if isinstance(expression, Literal):
            self._emit(MirConst(target, expression.value, self._type_of(expression), expression.location))
        elif isinstance(expression, Identifier):
            self._emit(
                MirLoad(
                    target,
                    self._resolve_binding_name(expression.name),
                    self._type_of(expression),
                    expression.location,
                )
            )
        else:
            raise AssertionError(type(expression).__name__)
        return target


def _report_and_match(*, exhaustive: bool = True):
    loc = SourceLocation(1, 1)
    checker = TypedHIRChecker(Program(()))
    checker.scopes.append({"choice": generic("Option", INT)})
    arms = (
        MatchArm("Some", "payload", Identifier("payload", loc), loc),
        MatchArm("None", None, Literal(0, loc), loc),
    ) if exhaustive else (
        MatchArm("Some", "payload", Identifier("payload", loc), loc),
    )
    expression = MatchExpression(Identifier("choice", loc), arms, loc)
    checker.infer(expression)
    report = TypedHIRReport(
        tuple(checker.bindings),
        tuple(checker.expressions),
        checker.collections,
        tuple(checker.match_resolutions),
    )
    return report, expression


def test_match_cfg_uses_one_scrutinee_and_compiler_owned_variant_identities():
    report, expression = _report_and_match()
    lowerer = _FakeLowerer(report, expression)

    result = lower_match_expression_v1(lowerer, expression)

    assert isinstance(result, int)
    assert lowerer.scrutinee_evaluations == 1
    tests = [
        item
        for block in lowerer.blocks.values()
        for item in block.instructions
        if isinstance(item, MirVariantIs)
    ]
    assert [item.variant for item in tests] == ["Option::Some", "Option::None"]
    assert len({item.source for item in tests}) == 1


def test_payload_is_emitted_only_for_payload_arm_and_same_canonical_identity():
    report, expression = _report_and_match()
    lowerer = _FakeLowerer(report, expression)

    lower_match_expression_v1(lowerer, expression)

    tests = [
        item
        for block in lowerer.blocks.values()
        for item in block.instructions
        if isinstance(item, MirVariantIs)
    ]
    payloads = [
        item
        for block in lowerer.blocks.values()
        for item in block.instructions
        if isinstance(item, MirVariantPayload)
    ]
    assert len(payloads) == 1
    assert payloads[0].variant == "Option::Some"
    assert payloads[0].source == tests[0].source

    some_test_block = next(
        block for block in lowerer.blocks.values() if tests[0] in block.instructions
    )
    assert isinstance(some_test_block.terminator, MirBranch)
    payload_block = next(
        block for block in lowerer.blocks.values() if payloads[0] in block.instructions
    )
    assert payload_block.id == some_test_block.terminator.then_block


def test_exhaustive_match_ends_final_miss_edge_in_unreachable_not_default_arm():
    report, expression = _report_and_match()
    lowerer = _FakeLowerer(report, expression)

    lower_match_expression_v1(lowerer, expression)

    unreachable = [
        block for block in lowerer.blocks.values() if isinstance(block.terminator, MirUnreachable)
    ]
    assert len(unreachable) == 1
    assert "exhaustive match" in unreachable[0].terminator.reason


def test_non_exhaustive_match_refuses_executable_mir():
    report, expression = _report_and_match(exhaustive=False)
    lowerer = _FakeLowerer(report, expression)

    with pytest.raises(MirMatchPlanError, match="non-exhaustive"):
        lower_match_expression_v1(lowerer, expression)
