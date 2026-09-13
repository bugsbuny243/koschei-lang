from koschei import mir
from koschei.mir_canonical_lowering_v1 import lower_function_blocks_v1


def test_production_mir_uses_canonical_lowering_entry_point() -> None:
    assert mir.lower_function_blocks_v1 is lower_function_blocks_v1
    assert (
        mir.lower_function_blocks_v1.__module__
        == "koschei.mir_canonical_lowering_v1"
    )
