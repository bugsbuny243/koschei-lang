from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from koschei.capability_effect_contract_v1 import NET_IO, POWER_DOMAIN_NETWORK
from koschei.compiler_capability_effect_basis_v1 import (
    CompilerCapabilityEffectBasisV1Error,
    derive_compiler_capability_effect_basis_v1,
)
from koschei.mir import require_mir
from koschei.modules import check_graph, load_graph


def compiler_mir(source: str):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "authority.ks"
    path.write_text(source, encoding="utf-8")
    graph = load_graph(path)
    check_graph(graph)
    return directory, require_mir(graph)


def test_basis_derives_exact_capability_call_from_sealed_compiler_mir():
    directory, mir = compiler_mir(
        '''
fn execute(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("network")
    return response.text()
}
fn main() { println("ready") }
'''
    )
    try:
        basis = derive_compiler_capability_effect_basis_v1(
            mir,
            module_name="authority",
            function_name="execute",
        )
        assert basis.mir_fingerprint == mir.fingerprint
        assert basis.capability_type == "NetCaps"
        assert basis.capability_method == "get"
        assert basis.canonical_effect == NET_IO
        assert basis.power_domain == POWER_DOMAIN_NETWORK
        assert basis.authority is False
        basis.assert_matches_mir(mir)
    finally:
        directory.cleanup()


def test_multiple_direct_capability_calls_are_ambiguous_and_fail_closed():
    directory, mir = compiler_mir(
        '''
fn execute(net: NetCaps, url: String) -> String or Error {
    let first = net.get(url) or return Error("first")
    let second = net.get(url) or return Error("second")
    return second.text()
}
fn main() { println("ready") }
'''
    )
    try:
        with pytest.raises(
            CompilerCapabilityEffectBasisV1Error,
            match="exactly one direct capability call",
        ):
            derive_compiler_capability_effect_basis_v1(
                mir,
                module_name="authority",
                function_name="execute",
            )
    finally:
        directory.cleanup()


def test_local_call_indirection_is_not_guessed_in_basis_v1():
    directory, mir = compiler_mir(
        '''
fn fetch(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("network")
    return response.text()
}
fn execute(net: NetCaps, url: String) -> String or Error {
    return fetch(net, url) or return Error("execute")
}
fn main() { println("ready") }
'''
    )
    try:
        with pytest.raises(
            CompilerCapabilityEffectBasisV1Error,
            match="leaf function without local calls",
        ):
            derive_compiler_capability_effect_basis_v1(
                mir,
                module_name="authority",
                function_name="execute",
            )
    finally:
        directory.cleanup()


def test_imported_call_indirection_is_not_guessed_in_basis_v1():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "risk.ks").write_text(
            '''
fn fetch(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("network")
    return response.text()
}
''',
            encoding="utf-8",
        )
        (root / "authority.ks").write_text(
            '''
import risk
fn execute(net: NetCaps, url: String) -> String or Error {
    return risk.fetch(net, url) or return Error("execute")
}
fn main() { println("ready") }
''',
            encoding="utf-8",
        )
        graph = load_graph(root / "authority.ks")
        check_graph(graph)
        mir = require_mir(graph)
        with pytest.raises(
            CompilerCapabilityEffectBasisV1Error,
            match="leaf function without imported calls",
        ):
            derive_compiler_capability_effect_basis_v1(
                mir,
                module_name="authority",
                function_name="execute",
            )


def test_tampered_basis_no_longer_matches_sealed_compiler_mir():
    directory, mir = compiler_mir(
        '''
fn execute(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("network")
    return response.text()
}
fn main() { println("ready") }
'''
    )
    try:
        basis = derive_compiler_capability_effect_basis_v1(
            mir,
            module_name="authority",
            function_name="execute",
        )
        forged = replace(basis, capability_method="post")
        with pytest.raises(
            CompilerCapabilityEffectBasisV1Error,
            match="basis seal mismatch|canonical effect",
        ):
            forged.assert_matches_mir(mir)
    finally:
        directory.cleanup()
