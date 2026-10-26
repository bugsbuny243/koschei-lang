"""Compatibility re-exports for stabilized staged MIR container instructions.

Canonical class identity lives in ``mir_extension_instructions_v4``. This module
exists only to preserve imports while callers migrate; it MUST NOT redefine MIR
instruction dataclasses or become a second instruction authority.
"""
from .mir_extension_instructions_v4 import (
    MirIsRuntimeError,
    MirMapContains,
    MirMapFinish,
    MirMapGet,
    MirMapInsert,
    MirMapKeys,
    MirMapNew,
    MirMapSet,
    MirStructFinish,
    MirStructNew,
    MirStructSet,
)

__all__ = [
    "MirIsRuntimeError",
    "MirMapContains",
    "MirMapFinish",
    "MirMapGet",
    "MirMapInsert",
    "MirMapKeys",
    "MirMapNew",
    "MirMapSet",
    "MirStructFinish",
    "MirStructNew",
    "MirStructSet",
]
