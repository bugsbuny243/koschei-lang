from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
import tempfile

import pytest

from koschei.interpreter import KsError, KsUnit
from koschei.mir import MirGraph, _fingerprint, _resource_contract, require_mir
from koschei.mir_executor_v1 import MirExecutionError, MirExecutorV1, execute_mir_v1
from koschei.mir_ir import MirAstFallback, MirBasicBlock, MirReturn
from koschei.modules import check_graph, load_graph
from koschei.type_system import VOID


def _compiler_mir(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "runtime.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, require_mir(graph)


def test_executor_runs_local_function_from_mir_frames(capsys):
    directory, mir = _compiler_mir(
        '''
fn add(left: Int, right: Int) -> Int {
    return left + right
}
fn main() {
    println(add(2, 3))
}
'''
    )
    try:
        result = execute_mir_v1(mir)
        assert result is KsUnit
        assert capsys.readouterr().out == "5\n"
    finally:
        directory.cleanup()


def test_or_return_executes_success_and_failure_in_mir_frames():
    directory, mir = _compiler_mir(
        '''
fn source(ok: Bool) -> String or Error {
    if ok { return "yes" }
    return Error("no")
}
fn unwrap(ok: Bool) -> String or Error {
    let value = source(ok) or return Error("wrapped")
    return value
}
fn main() {}
'''
    )
    try:
        executor = MirExecutorV1(mir)
        module_key = mir.root_module.key
        assert executor._call(module_key, "unwrap", [True]) == "yes"
        failure = executor._call(module_key, "unwrap", [False])
        assert isinstance(failure, KsError)
        assert failure.message == "wrapped"
        unwrap = next(item for item in mir.root_module.functions if item.name == "unwrap")
        assert unwrap.resources.ast_fallbacks == 0
    finally:
        directory.cleanup()


def test_executor_rejects_sealed_ast_fallback_instead_of_running_source_ast():
    directory, mir = _compiler_mir('fn main() { println("safe") }')
    try:
        root = mir.root_module
        main = next(item for item in root.functions if item.name == "main")
        location = main.declaration.location
        blocks = (
            MirBasicBlock(
                0,
                (MirAstFallback(None, "SyntheticFallback", VOID, location),),
                MirReturn(None),
            ),
        )
        forged_main = replace(
            main,
            blocks=blocks,
            resources=_resource_contract(main.name, main.calls, blocks),
        )
        forged_root = replace(
            root,
            functions=tuple(
                forged_main if item.name == "main" else item
                for item in root.functions
            ),
        )
        modules = MappingProxyType(
            {
                key: forged_root if key == mir.root else module
                for key, module in mir.modules.items()
            }
        )
        forged = MirGraph(mir.root, modules, "")
        object.__setattr__(forged, "fingerprint", _fingerprint(forged.root, forged.modules))
        forged.assert_sealed()

        with pytest.raises(MirExecutionError, match="AST fallback"):
            execute_mir_v1(forged)
    finally:
        directory.cleanup()
