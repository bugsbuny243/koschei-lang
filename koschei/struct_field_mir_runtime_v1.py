"""Install canonical runtime handling for ``MirStructFieldSet``.

Koschei still uses explicit compatibility installers while MIR v4 authority is
being consolidated.  This installer extends the sealed MIR executor with one
AST-free instruction and delegates the runtime law to ``struct_field_runtime_v1``.
"""
from __future__ import annotations

from .mir_extension_instructions_v4 import MirStructFieldSet
from .struct_field_runtime_v1 import struct_field_set_v1


_INSTALLED_MARKER = "_koschei_struct_field_set_v1_installed"


def install_struct_field_mir_runtime_v1() -> None:
    from .mir_executor_v1 import MirExecutorV1

    current = MirExecutorV1._execute_instruction
    if getattr(current, _INSTALLED_MARKER, False):
        return

    def _execute_instruction(self, module_key, instruction, values, bindings):
        if isinstance(instruction, MirStructFieldSet):
            values[instruction.target] = struct_field_set_v1(
                values[instruction.object],
                instruction.field,
                values[instruction.source],
                structs=self.mir.structs(),
                contains_capability=self.primitives.contains_capability,
                matches_type=self.primitives.matches_type,
                runtime_type_name=self.primitives.runtime_type_name,
                location=instruction.location,
            )
            return
        return current(self, module_key, instruction, values, bindings)

    setattr(_execute_instruction, _INSTALLED_MARKER, True)
    MirExecutorV1._execute_instruction = _execute_instruction


__all__ = ["install_struct_field_mir_runtime_v1"]
