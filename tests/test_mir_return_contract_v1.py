from pathlib import Path
import tempfile

import pytest

from koschei.mir import require_mir
from koschei.mir_executor_v1 import MirExecutionError, MirExecutorV1
from koschei.modules import check_graph, load_graph
from koschei.runtime_primitive_facade_v1 import RuntimePrimitiveFacadeV1


def _executor(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "return_contract.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, MirExecutorV1(require_mir(graph))


def test_mir_executor_does_not_bypass_return_contract_for_error_values(monkeypatch):
    directory, executor = _executor(
        '''
fn helper() -> Error { return Error("boom") }
fn main() { helper() }
'''
    )
    original = RuntimePrimitiveFacadeV1.matches_type

    def reject_error_for_contract_probe(self, value, expected_names):
        if self.runtime_type_name(value) == "Error":
            return False
        return original(self, value, expected_names)

    monkeypatch.setattr(
        RuntimePrimitiveFacadeV1,
        "matches_type",
        reject_error_for_contract_probe,
    )
    try:
        with pytest.raises(MirExecutionError, match="dönüş sözleşmesi"):
            executor.execute_main()
    finally:
        directory.cleanup()
