from __future__ import annotations

import unittest

from koschei.capability_effect_contract_v1 import (
    DISK_READ,
    DISK_WRITE,
    ENV_READ,
    NET_IO,
    PROCESS_EXEC,
    effect_for,
)
from koschei.effect_contracts_v1 import infer_effect_contracts
from koschei.effects import infer_effects
from koschei.parser import parse
from koschei.typed_hir import check_typed_hir


class CapabilityEffectAlignmentTests(unittest.TestCase):
    def test_canonical_names_cover_side_effect_capabilities(self) -> None:
        self.assertEqual(effect_for("NetCaps", "get"), NET_IO)
        self.assertEqual(effect_for("DiskReadCaps", "read"), DISK_READ)
        self.assertEqual(effect_for("DiskCaps", "write"), DISK_WRITE)
        self.assertEqual(effect_for("EnvCaps", "get"), ENV_READ)
        self.assertEqual(effect_for("ProcessCaps", "run"), PROCESS_EXEC)

    def test_source_and_mir_engines_share_network_effect_name(self) -> None:
        program = parse(
            '''
fn fetch(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("net")
    return response.text()
}
'''
        )
        typed = check_typed_hir(program, {})
        source_effects = infer_effect_contracts(program, {}, typed)["fetch"]
        mir_effects = infer_effects(program)["fetch"][1]
        self.assertIn(NET_IO, source_effects.direct_effects)
        self.assertEqual(mir_effects, (NET_IO,))

    def test_source_and_mir_engines_share_process_effect_name(self) -> None:
        program = parse(
            '''
fn launch(process: ProcessCaps, command: String) -> String or Error {
    return process.run(command) or return Error("process")
}
'''
        )
        typed = check_typed_hir(program, {})
        source_effects = infer_effect_contracts(program, {}, typed)["launch"]
        mir_effects = infer_effects(program)["launch"][1]
        self.assertIn(PROCESS_EXEC, source_effects.direct_effects)
        self.assertEqual(mir_effects, (PROCESS_EXEC,))


if __name__ == "__main__":
    unittest.main()
