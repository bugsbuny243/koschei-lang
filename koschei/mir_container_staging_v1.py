"""Compatibility re-exports for stabilized staged MIR container instructions.

Canonical class identity lives in ``mir_extension_instructions_v4``. This module
exists only to preserve imports while callers migrate; it MUST NOT redefine MIR
instruction dataclasses or become a second instruction authority.
"""
from .mir_extension_instructions_v4 import (
    MirIsRuntimeError,
    MirMapFinish,
    MirMapInsert,
    MirMapNew,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
)

__all__ = [
    "MirIsRuntimeError",
    "MirMapFinish",
    "MirMapInsert",
    "MirMapNew",
    "MirStructFinish",
    "MirStructNew",
    "MirStructSet",
]
