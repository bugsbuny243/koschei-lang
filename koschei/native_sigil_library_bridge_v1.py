"""Bridge sealed native Koschei sigil MIR into Library expansion v1.

The Library must consume compiler-produced semantic state, not re-interpret raw
source. This bridge takes a sealed NativeSigilMir, reconstructs only the
canonical sigil sequence already committed by that MIR, verifies that the
Universe plan identity still matches, and then derives the Library expansion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .library_expansion_engine_v1 import LibraryExpansionPlan, compile_library_expansion
from .native_sigil_mir_v1 import NativeSigilMir
from .universe_kernel_v1 import compile_universe_plan

_CTX = b"koschei.native-sigil-library-bridge/v1\x00"


class NativeSigilLibraryBridgeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NativeSigilLibraryPlan:
    native_mir_fingerprint: str
    universe_plan_digest: str
    library_plan: LibraryExpansionPlan
    digest: str

    def assert_sealed(self) -> None:
        self.library_plan.steps and None
        expected = _digest(
            self.native_mir_fingerprint,
            self.universe_plan_digest,
            self.library_plan.digest,
        )
        if expected != self.digest:
            raise NativeSigilLibraryBridgeError("native sigil Library plan seal mismatch")


def _digest(mir_fingerprint: str, universe_digest: str, library_digest: str) -> str:
    payload = "\n".join(
        (
            f"mir={mir_fingerprint}",
            f"universe={universe_digest}",
            f"library={library_digest}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()


def expand_native_sigil_mir(mir: NativeSigilMir) -> NativeSigilLibraryPlan:
    """Derive a sealed Library work plan from sealed native sigil MIR."""

    mir.assert_sealed()
    sigils = tuple(binding.sigil for binding in mir.bindings)

    universe = compile_universe_plan(sigils)
    if universe.digest != mir.universe_plan_digest:
        raise NativeSigilLibraryBridgeError(
            "native sigil MIR universe identity no longer matches canonical Universe"
        )

    library = compile_library_expansion(sigils)
    if library.sigils != sigils:
        raise NativeSigilLibraryBridgeError(
            "Library expansion sigil sequence differs from compiler-produced MIR"
        )

    # compile_library_expansion builds on the activation engine, whose composed
    # base is the same canonical Universe plan. Re-check that identity here so
    # the Library cannot silently expand a different semantic universe.
    activation_universe = compile_universe_plan(library.sigils)
    if activation_universe.digest != mir.universe_plan_digest:
        raise NativeSigilLibraryBridgeError(
            "Library expansion is bound to a different Universe plan"
        )

    result = NativeSigilLibraryPlan(
        native_mir_fingerprint=mir.fingerprint,
        universe_plan_digest=mir.universe_plan_digest,
        library_plan=library,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _digest(result.native_mir_fingerprint, result.universe_plan_digest, library.digest),
    )
    result.assert_sealed()
    return result
