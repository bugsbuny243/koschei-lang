from pathlib import Path
import tempfile

from koschei.capability_effect_contract_v1 import NET_IO
from koschei.compiler_capability_effect_basis_v1 import (
    derive_compiler_capability_effect_basis_v1,
)
from koschei.mir import require_mir
from koschei.mir_capability_callsite_v1 import derive_mir_capability_callsites_v1
from koschei.modules import check_graph, load_graph


def test_nested_or_return_receiver_retains_one_sealed_capability_identity():
    source = '''
fn execute(net: NetCaps, url: String) -> String or Error {
    return (net.get(url) or return Error("network")).text()
}
fn main() { println("ready") }
'''

    with tempfile.TemporaryDirectory(prefix="koschei-mir-nested-capability-") as directory:
        path = Path(directory) / "authority.ks"
        path.write_text(source, encoding="utf-8")
        graph = load_graph(path)
        check_graph(graph)
        mir = require_mir(graph)

        sites = derive_mir_capability_callsites_v1(
            mir,
            module_name="authority",
            function_name="execute",
        )
        assert len(sites) == 1
        assert sites[0].capability_type == "NetCaps"
        assert sites[0].capability_method == "get"
        assert sites[0].canonical_effect == NET_IO
        assert sites[0].normalized_mir is True

        basis = derive_compiler_capability_effect_basis_v1(
            mir,
            module_name="authority",
            function_name="execute",
        )
        assert basis.capability_type == "NetCaps"
        assert basis.capability_method == "get"
        assert basis.canonical_effect == NET_IO
        assert basis.normalized_mir is True
        assert basis.compatibility_fallback is False
