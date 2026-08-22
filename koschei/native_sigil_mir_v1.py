"""Sealed MIR contract for native Koschei sigil programs v1.

This is the first bridge from parsed/typed native sigil declarations into an
intermediate representation that can be consumed by Library/Universe stages.
It is intentionally separate from the existing function MIR while that MIR
still contains AST fallback instructions. The two representations will be
joined only after the first native boundary slice has executable parity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .native_sigil_semantics_v1 import NativeSigilSemanticReport, check_native_sigils
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
                    f"location={binding.source_line}:{binding.source_column}",
                )
            )
        )
    return hashlib.sha256(_CTX + "\n".join(rows).encode("utf-8")).hexdigest()


def lower_native_sigils(
    program: NativeProgram,
    report: NativeSigilSemanticReport | None = None,
) -> NativeSigilMir:
    """Lower typed native sigil semantics into deterministic sealed MIR."""

    semantic = check_native_sigils(program) if report is None else report
    if not semantic.bindings:
        raise NativeSigilMirError("native program contains no sigil semantics")

    bindings = tuple(
        MirSigilBinding(
            sigil=item.declaration.sigil,
            subject=item.declaration.subject,
            semantic_domain=item.semantic_domain,
            may_grant_authority=item.may_grant_authority,
            obligations=item.obligations,
            source_line=item.declaration.location.line,
            source_column=item.declaration.location.column,
        )
        for item in semantic.bindings
    )
    result = NativeSigilMir(
        bindings=bindings,
        universe_plan_digest=semantic.universe_plan.digest,
        fingerprint="",
    )
    object.__setattr__(
        result,
        "fingerprint",
        _fingerprint(result.bindings, result.universe_plan_digest),
    )
    result.assert_sealed()
    return result
