"""Sealed MIR contract for native Koschei sigil programs v1.

This is the first bridge from parsed/typed native sigil declarations into an
intermediate representation that can be consumed by Library/Universe stages.
It is intentionally separate from the existing function MIR while that MIR
still contains AST fallback instructions. The two representations will be
joined only after the first native boundary slice has executable parity.

Source locations are diagnostic metadata only. They remain on bindings so tools
can point back to source, but they are deliberately excluded from the semantic
fingerprint: moving identical semantics to another line must not create another
Koschei reality.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .native_sigil_semantics_v1 import TypedSigilProgram, check_native_sigils
from .native_sigils_v1 import NativeProgram

_CTX = b"koschei.native-sigil-mir/v1\x00"


class NativeSigilMirError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MirSigilBinding:
    sigil: str
    subject: str
    semantic_domain: str
    may_grant_authority: bool
    obligations: tuple[str, ...]
    source_line: int
    source_column: int


@dataclass(frozen=True, slots=True)
class NativeSigilMir:
    bindings: tuple[MirSigilBinding, ...]
    universe_plan_digest: str
    fingerprint: str
    version: int = 1

    def assert_sealed(self) -> None:
        if not self.bindings:
            raise NativeSigilMirError("native sigil MIR requires at least one binding")
        if self.fingerprint != _fingerprint(self.bindings, self.universe_plan_digest):
            raise NativeSigilMirError("native sigil MIR fingerprint mismatch")


def _fingerprint(bindings: Iterable[MirSigilBinding], universe_digest: str) -> str:
    rows = [f"universe={universe_digest}"]
    for binding in bindings:
        rows.append(
            "|".join(
                (
                    f"sigil={binding.sigil}",
                    f"subject={binding.subject}",
                    f"domain={binding.semantic_domain}",
                    f"authority={int(binding.may_grant_authority)}",
                    "obligations=" + ",".join(binding.obligations),
                )
            )
        )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


def _require_report_matches_program(
    program: NativeProgram,
    report: TypedSigilProgram,
) -> TypedSigilProgram:
    """Reject semantic state that is stale, foreign, or tampered.

    Native MIR is a security boundary. A caller may cache typed semantics, but
    lowering must never accept a report produced for another source program or
    a report whose canonical sigil meaning has been modified after checking.
    Re-deriving the small native semantic surface keeps this boundary
    fail-closed until TypedSigilProgram owns an independent seal API.
    """

    canonical = check_native_sigils(program)
    if report != canonical:
        raise NativeSigilMirError(
            "native sigil semantic report does not match the supplied program"
        )
    return report


def lower_native_sigils(
    program: NativeProgram,
    report: TypedSigilProgram | None = None,
) -> NativeSigilMir:
    """Lower typed native sigil semantics into deterministic sealed MIR."""

    if not isinstance(program, NativeProgram):
        raise NativeSigilMirError("native sigil MIR lowering requires NativeProgram")

    semantic = (
        check_native_sigils(program)
        if report is None
        else _require_report_matches_program(program, report)
    )
    if not semantic.declarations:
        raise NativeSigilMirError("native program contains no sigil semantics")
    if len(semantic.declarations) != len(program.sigils):
        raise NativeSigilMirError("native sigil semantic declaration count mismatch")

    bindings: list[MirSigilBinding] = []
    for declaration, typed in zip(program.sigils, semantic.declarations, strict=True):
        if (declaration.sigil, declaration.subject) != (typed.sigil, typed.subject):
            raise NativeSigilMirError(
                "native sigil semantic declaration identity mismatch"
            )
        bindings.append(
            MirSigilBinding(
                sigil=typed.sigil,
                subject=typed.subject,
                semantic_domain=typed.semantic_domain,
                may_grant_authority=typed.may_grant_authority,
                obligations=typed.obligations,
                source_line=declaration.location.line,
                source_column=declaration.location.column,
            )
        )

    result = NativeSigilMir(
        bindings=tuple(bindings),
        universe_plan_digest=semantic.universe_plan_digest,
        fingerprint="",
    )
    object.__setattr__(
        result,
        "fingerprint",
        _fingerprint(result.bindings, result.universe_plan_digest),
    )
    result.assert_sealed()
    return result
