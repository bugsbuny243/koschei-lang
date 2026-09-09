from pathlib import Path
import tempfile

from koschei.interpreter import KsError, KsUnit, StructValue
from koschei.mir import require_mir
from koschei.mir_container_staging_v1 import (
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
)
from koschei.mir_executor_v1 import MirExecutorV1, execute_mir_v1
from koschei.modules import check_graph, load_graph


def _compiler_mir(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "container.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, require_mir(graph)


def _instructions(function):
    return tuple(
        instruction
        for block in function.blocks
        for instruction in block.instructions
    )


def test_map_literal_lowers_without_ast_fallback_and_executes_from_mir() -> None:
    directory, mir = _compiler_mir(
        '''
fn make_map() -> Map<String, Int> {
    return {"a": 1, "b": 2}
}
fn main() {}
'''
    )
    try:
        function = next(item for item in mir.root_module.functions if item.name == "make_map")
        instructions = _instructions(function)
        assert function.resources.ast_fallbacks == 0
        assert any(isinstance(item, MirMapNew) for item in instructions)
        assert sum(isinstance(item, MirMapInsert) for item in instructions) == 2
        assert any(isinstance(item, MirMapFinish) for item in instructions)

        executor = MirExecutorV1(mir)
        value = executor._call(mir.root_module.key, "make_map", [])
        assert value == {"a": 1, "b": 2}
    finally:
        directory.cleanup()


def test_struct_literal_lowers_without_ast_fallback_and_executes_from_mir() -> None:
    directory, mir = _compiler_mir(
        '''
struct Profile { name: String, age: Int }
fn make_profile() -> Profile {
    return Profile { name: "Ada", age: 37 }
}
fn main() {}
'''
    )
    try:
        function = next(item for item in mir.root_module.functions if item.name == "make_profile")
        instructions = _instructions(function)
        assert function.resources.ast_fallbacks == 0
        assert any(isinstance(item, MirStructNew) for item in instructions)
        assert sum(isinstance(item, MirStructSet) for item in instructions) == 2
        assert any(isinstance(item, MirStructFinish) for item in instructions)

        executor = MirExecutorV1(mir)
        value = executor._call(mir.root_module.key, "make_profile", [])
        assert isinstance(value, StructValue)
        assert value.type_name == "Profile"
        assert value.fields == {"name": "Ada", "age": 37}
    finally:
        directory.cleanup()


def test_map_runtime_error_skips_later_effectful_value(capsys) -> None:
    directory, mir = _compiler_mir(
        '''
fn late() -> Int {
    println("late")
    return 2
}
fn make_map() -> Map<String, Int> or Error {
    return {"a": 1 / 0, "b": late()}
}
fn main() {}
'''
    )
    try:
        function = next(item for item in mir.root_module.functions if item.name == "make_map")
        instructions = _instructions(function)
        assert function.resources.ast_fallbacks == 0
        assert sum(isinstance(item, MirIsRuntimeError) for item in instructions) >= 4

        executor = MirExecutorV1(mir)
        result = executor._call(mir.root_module.key, "make_map", [])
        assert isinstance(result, KsError)
        assert capsys.readouterr().out == ""
    finally:
        directory.cleanup()


def test_struct_runtime_error_skips_later_effectful_field(capsys) -> None:
    directory, mir = _compiler_mir(
        '''
struct Profile { age: Int, name: String }
fn late_name() -> String {
    println("late-name")
    return "Ada"
}
fn make_profile() -> Profile or Error {
    return Profile { age: 1 / 0, name: late_name() }
}
fn main() {}
'''
    )
    try:
        executor = MirExecutorV1(mir)
        result = executor._call(mir.root_module.key, "make_profile", [])
        assert isinstance(result, KsError)
        assert capsys.readouterr().out == ""
    finally:
        directory.cleanup()


def test_public_main_can_construct_map_and_struct_without_ast_execution() -> None:
    directory, mir = _compiler_mir(
        '''
struct Profile { name: String, age: Int }
fn main() {
    let metadata = {"a": 1}
    let profile = Profile { name: "Ada", age: 37 }
    println(metadata.contains("a"))
    println(profile.name)
}
'''
    )
    try:
        result = execute_mir_v1(mir)
        assert result is KsUnit
    finally:
        directory.cleanup()
