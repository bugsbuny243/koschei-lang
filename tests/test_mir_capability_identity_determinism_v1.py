from pathlib import Path
import tempfile

import pytest

from koschei.compiler_capability_effect_basis_v1 import (
    CompilerCapabilityEffectBasisV1Error,
    derive_compiler_capability_effect_basis_v1,
)
from koschei.mir import require_mir
from koschei.mir_capability_callsite_v1 import derive_mir_capability_callsites_v1
from koschei.modules import check_graph, load_graph


_CAPABILITY_SOURCE = '''
fn execute(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("network")
    return response.text()
}
fn main() { println("ready") }
'''


def _checked_mir(path: Path, source: str):
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return require_mir(graph)


def test_same_checked_source_produces_same_capability_identity_and_digest():
    with tempfile.TemporaryDirectory(prefix="koschei-mir-determinism-") as directory:
        path = Path(directory) / "authority.ks"
        first = _checked_mir(path, _CAPABILITY_SOURCE)
        second = _checked_mir(path, _CAPABILITY_SOURCE)

        first_sites = derive_mir_capability_callsites_v1(
            first,
            module_name="authority",
            function_name="execute",
        )
        second_sites = derive_mir_capability_callsites_v1(
            second,
            module_name="authority",
            function_name="execute",
        )

        assert first.fingerprint == second.fingerprint
        assert first_sites == second_sites
        assert len(first_sites) == 1
        assert first_sites[0].digest == second_sites[0].digest


def test_plain_value_method_does_not_become_capability_identity():
    source = '''
fn clean(value: String) -> String {
    return value.trim()
}
fn main() { println("ready") }
'''
    with tempfile.TemporaryDirectory(prefix="koschei-mir-non-capability-") as directory:
        mir = _checked_mir(Path(directory) / "authority.ks", source)
        sites = derive_mir_capability_callsites_v1(
            mir,
            module_name="authority",
            function_name="clean",
        )
        assert sites == ()

        with pytest.raises(
            CompilerCapabilityEffectBasisV1Error,
            match="exactly one normalized MIR capability call",
        ):
            derive_compiler_capability_effect_basis_v1(
                mir,
                module_name="authority",
                function_name="clean",
            )
