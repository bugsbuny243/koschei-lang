from pathlib import Path
import tempfile

import pytest

from koschei.ast_nodes import SourceLocation
from koschei.mir import require_mir
from koschei.mir_executor_v1 import MirExecutorV1
from koschei.modules import check_graph, load_graph
from koschei.runtime_primitive_facade_v1 import RuntimePrimitiveFacadeError


def _executor(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "facade.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, MirExecutorV1(require_mir(graph))


def test_mir_executor_has_no_direct_reference_interpreter_escape_surface():
    directory, executor = _executor(
        '''
fn helper() -> Int { return 7 }
fn main() { println(helper()) }
'''
    )
    try:
        assert not hasattr(executor, "runtime")
        assert hasattr(executor, "primitives")
    finally:
        directory.cleanup()


def test_primitive_facade_rejects_source_function_declaration():
    directory, executor = _executor(
        '''
fn helper() -> Int { return 7 }
fn main() {}
'''
    )
    try:
        helper = next(
            item for item in executor.mir.root_module.functions if item.name == "helper"
        )
        with pytest.raises(
            RuntimePrimitiveFacadeError,
            match="source AST fonksiyonu",
        ):
            executor.primitives.invoke_primitive(
                helper.declaration,
                [],
                SourceLocation(1, 1),
            )
    finally:
        directory.cleanup()


def test_builtin_primitive_still_works_through_narrow_facade(capsys):
    directory, executor = _executor('fn main() { println("ok") }')
    try:
        result = executor.execute_main()
        assert str(result) == "unit"
        assert capsys.readouterr().out == "ok\n"
    finally:
        directory.cleanup()
