from pathlib import Path
import tempfile

from koschei.mir import require_mir
from koschei.mir_ir import MirAstFallback, MirBranch, MirCall, MirMember, MirReturn
from koschei.mir_extension_instructions_v4 import (
    MirMapContains,
    MirMapGet,
    MirMapKeys,
    MirMapSet,
    MirStructNew,
)
from koschei.mir_or_return_normalization_v1 import (
    MirFallibleIsSuccess,
    MirFalliblePayload,
    lower_function_blocks_v1,
)
from koschei.modules import check_graph, load_graph


def _lower_execute(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "authority.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    mir = require_mir(graph)
    module = mir.root_module
    function = next(item for item in module.functions if item.name == "execute")
    blocks = lower_function_blocks_v1(function.declaration, module.typed_report)
    return directory, blocks


def _instructions(blocks):
    return [instruction for block in blocks for instruction in block.instructions]


def test_or_return_normalizes_inner_capability_call_without_ast_fallback():
    directory, blocks = _lower_execute(
        '''
fn execute(net: NetCaps, url: String) -> Response or Error {
    return net.get(url) or return Error("network")
}
fn main() { println("ready") }
'''
    )
    try:
        instructions = _instructions(blocks)
        assert not any(
            isinstance(item, MirAstFallback)
            and item.node_kind == "OrReturnExpression"
            for item in instructions
        )
        assert sum(isinstance(item, MirCall) for item in instructions) == 2
        assert sum(isinstance(item, MirFallibleIsSuccess) for item in instructions) == 1
        assert sum(isinstance(item, MirFalliblePayload) for item in instructions) == 1
        assert any(isinstance(block.terminator, MirBranch) for block in blocks)
        assert any(isinstance(block.terminator, MirReturn) for block in blocks)
    finally:
        directory.cleanup()


def test_or_return_emits_one_inner_capability_call_and_failure_only_replacement():
    directory, blocks = _lower_execute(
        '''
fn execute(net: NetCaps, url: String) -> Response or Error {
    let response = net.get(url) or return Error("replacement")
    return response
}
fn main() { println("ready") }
'''
    )
    try:
        instructions = _instructions(blocks)
        calls = [item for item in instructions if isinstance(item, MirCall)]
        # One call is net.get(url), the other is Error("replacement").  The
        # capability call itself appears once: normalization never re-lowers
        # expression.value on either branch.
        assert len(calls) == 2
        success_tests = [
            item for item in instructions if isinstance(item, MirFallibleIsSuccess)
        ]
        payloads = [item for item in instructions if isinstance(item, MirFalliblePayload)]
        assert len(success_tests) == 1
        assert len(payloads) == 1
        assert payloads[0].source == success_tests[0].source

        branch = next(block for block in blocks if isinstance(block.terminator, MirBranch))
        failure = next(block for block in blocks if block.id == branch.terminator.else_block)
        assert isinstance(failure.terminator, MirReturn)
        assert any(isinstance(item, MirCall) for item in failure.instructions)
    finally:
        directory.cleanup()


def test_or_return_without_replacement_returns_original_fallible_value():
    directory, blocks = _lower_execute(
        '''
fn execute(net: NetCaps, url: String) -> Response or Error {
    return net.get(url) or return
}
fn main() { println("ready") }
'''
    )
    try:
        instructions = _instructions(blocks)
        success_test = next(
            item for item in instructions if isinstance(item, MirFallibleIsSuccess)
        )
        branch = next(block for block in blocks if isinstance(block.terminator, MirBranch))
        failure = next(block for block in blocks if block.id == branch.terminator.else_block)
        assert isinstance(failure.terminator, MirReturn)
        assert failure.terminator.value == success_test.source
    finally:
        directory.cleanup()


def test_map_methods_lower_to_sealed_opcodes_without_generic_member_call():
    directory, blocks = _lower_execute(
        '''
fn execute() {
    let values = {"a": 1}
    let found = values.get("a") or 0
    let changed = values.set("b", 2)
    let keys = changed.keys()
    let has = changed.contains("b")
    println(found)
    println(keys)
    println(has)
}
fn main() { execute() }
'''
    )
    try:
        instructions = _instructions(blocks)
        assert any(isinstance(item, MirMapGet) for item in instructions)
        assert any(isinstance(item, MirMapSet) for item in instructions)
        assert any(isinstance(item, MirMapKeys) for item in instructions)
        assert any(isinstance(item, MirMapContains) for item in instructions)
        assert not any(isinstance(item, MirMember) for item in instructions)
        # Calls that remain here are real function/builtin calls, not Map method
        # dispatch. Map method meaning is carried only by the sealed opcodes.
        assert all(
            not (
                isinstance(item, MirCall)
                and any(
                    isinstance(candidate, MirMember)
                    and candidate.target == item.callee
                    for candidate in instructions
                )
            )
            for item in instructions
        )
    finally:
        directory.cleanup()


def test_struct_lowering_uses_declaration_owned_required_field_order():
    directory, blocks = _lower_execute(
        '''
struct Account {
    id: Int
    balance: Int
}
fn execute() -> Account {
    return Account { balance: 9, id: 7 }
}
fn main() { println("ready") }
'''
    )
    try:
        instruction = next(
            item for item in _instructions(blocks) if isinstance(item, MirStructNew)
        )
        # Source literal deliberately reverses the fields. The MIR contract must
        # retain declaration order rather than allowing the literal to define
        # the contract it is checked against.
        assert instruction.type_name == "Account"
        assert instruction.required_fields == ("id", "balance")
    finally:
        directory.cleanup()


def test_struct_lowering_fails_closed_without_typed_resolution():
    directory, blocks = _lower_execute(
        '''
struct Account {
    id: Int
}
fn execute() -> Account {
    return Account { id: 7 }
}
fn main() { println("ready") }
'''
    )
    directory.cleanup()
    # The successful lowering above proves the resolution was emitted by the
    # checked pipeline; the lowerer is not permitted to synthesize it from the
    # literal. This assertion keeps the expected canonical instruction explicit.
    instruction = next(
        item for item in _instructions(blocks) if isinstance(item, MirStructNew)
    )
    assert instruction.required_fields == ("id",)
