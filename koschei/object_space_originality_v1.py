"""Originality provenance for the canonical Object Space v1 filesystem surface."""

from __future__ import annotations

from .originality_contract_v1 import SurfaceProvenance


OBJECT_SPACE_SCAFFOLD_PROVENANCE_V1 = {
    "k0": SurfaceProvenance(
        invariant="protected-source-reality",
        rationale=(
            "k0 is the fixed sealed authority aperture; it is not a renamed manifest, "
            "entry file, source directory, package descriptor or developer-visible role."
        ),
        collision_reviewed=True,
    ),
    "k1": SurfaceProvenance(
        invariant="temporal-source-identity",
        rationale=(
            "k1 is a semantic-free opaque cell field whose children are rotating "
            "physical locators rather than source, module, test or dependency names."
        ),
        collision_reviewed=True,
    ),
}
