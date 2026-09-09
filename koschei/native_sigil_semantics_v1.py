"""Typed semantic binding for native Koschei sigil declarations v1.

This bridge turns real `.ks` sigil syntax into Koschei Universe semantics. It
intentionally does not execute effects, but it MUST reject semantic roots that
cannot be tied to an admitted Koschei identity. A sigil subject is therefore a
semantic reference, not an arbitrary label.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .native_sigils_v1 import NativeProgram, SigilDeclaration
from .universe_kernel_v1 import (
    UniverseKernelError,
    compile_universe_plan,
    sigil_spec,
)

_CTX = b"koschei.native-sigil-semantics/v1\x00"


class NativeSigilSemanticError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TypedSigilDeclaration:
    sigil: str
    subject: str
    semantic_domain: str
    obligations: tuple[str, ...]
    may_grant_authority: bool
    fail_closed: bool
    digest: str


@dataclass(frozen=True, slots=True)
class TypedSigilProgram:
    declarations: tuple[TypedSigilDeclaration, ...]
    universe_plan_digest: str
    digest: str


def _declaration_digest(declaration: SigilDeclaration) -> str:
    spec = sigil_spec(declaration.sigil)
    parts = (
        declaration.sigil,
        declaration.subject,
        spec.semantic_domain,
        ",".join(spec.obligations),
        str(int(spec.may_grant_authority)),
        str(int(spec.fail_closed)),
    )
    return hashlib.sha256(_CTX + "|".join(parts).encode("utf-8")).hexdigest()


def _require_admitted_subject_lineage(program: NativeProgram) -> None:
    """Require every non-genesis root to target a prior `ka` admission.

    `ka` establishes recognized existence with zero ambient authority. `vor`,
    `shi`, `thal`, and `nur` may refine what can happen to that admitted subject,
    but none of them may manufacture a subject merely by spelling a new name.
    This is the minimum executable form of the lexicon laws
    `identity-before-authority` and `observation/recovery/visibility cannot invent
    identity or authority`.
    """

    admitted: set[str] = set()
    for declaration in program.sigils:
        if declaration.sigil == "ka":
            admitted.add(declaration.subject)
            continue
        if declaration.subject not in admitted:
            raise NativeSigilSemanticError(
                f"{declaration.sigil} subject {declaration.subject!r} has no preceding "
                "ka admission"
            )


def check_native_sigils(program: NativeProgram) -> TypedSigilProgram:
    """Bind parsed native sigils to canonical Universe semantics.

    The Universe kernel owns sigil order/composition rules. This checker adds the
    identity-lineage rule that makes subjects real semantic references: every
    non-`ka` root must descend from an admitted subject in the same checked
    native program.
    """

    if not isinstance(program, NativeProgram):
        raise NativeSigilSemanticError("native sigil checking requires NativeProgram")
    if not program.sigils:
        return TypedSigilProgram((), "", hashlib.sha256(_CTX).hexdigest())

    seen: set[tuple[str, str]] = set()
    for declaration in program.sigils:
        key = (declaration.sigil, declaration.subject)
        if key in seen:
            raise NativeSigilSemanticError(
                f"duplicate native sigil subject: {declaration.sigil} {declaration.subject}"
            )
        seen.add(key)

    try:
        plan = compile_universe_plan(declaration.sigil for declaration in program.sigils)
    except UniverseKernelError as error:
        raise NativeSigilSemanticError(str(error)) from error

    _require_admitted_subject_lineage(program)

    typed: list[TypedSigilDeclaration] = []
    for declaration in program.sigils:
        spec = sigil_spec(declaration.sigil)
        typed.append(
            TypedSigilDeclaration(
                sigil=declaration.sigil,
                subject=declaration.subject,
                semantic_domain=spec.semantic_domain,
                obligations=spec.obligations,
                may_grant_authority=spec.may_grant_authority,
                fail_closed=spec.fail_closed,
                digest=_declaration_digest(declaration),
            )
        )

    digest_parts = [f"universe={plan.digest}"]
    digest_parts.extend(f"decl={item.digest}" for item in typed)
    digest = hashlib.sha256(_CTX + "\n".join(digest_parts).encode("utf-8")).hexdigest()
    return TypedSigilProgram(tuple(typed), plan.digest, digest)
