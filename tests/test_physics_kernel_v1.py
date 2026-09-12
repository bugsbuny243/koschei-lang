from dataclasses import replace

import pytest

from koschei.physics_kernel_v1 import (
    CANONICAL_PHYSICS_DIGEST_V1,
    CANONICAL_PHYSICS_LAWS_V1,
    PhysicsKernelError,
    canonical_physics_v1,
)


def test_physics_v1_has_exactly_twelve_unique_public_laws():
    physics = canonical_physics_v1()
    assert len(physics.laws) == 12
    assert len(set(physics.laws)) == 12
    assert physics.laws == CANONICAL_PHYSICS_LAWS_V1
    assert physics.digest == CANONICAL_PHYSICS_DIGEST_V1
    assert physics.authority is False


def test_physics_registry_cannot_be_rewritten_under_v1_identity():
    physics = canonical_physics_v1()
    weakened = replace(
        physics,
        laws=tuple(
            "physics.ambiguity.allow-by-default"
            if law == "physics.ambiguity.fail-closed"
            else law
            for law in physics.laws
        ),
    )
    with pytest.raises(PhysicsKernelError, match="substitution"):
        weakened.assert_canonical()


def test_physics_registry_cannot_be_promoted_to_authority():
    forged = replace(canonical_physics_v1(), authority=True)
    with pytest.raises(PhysicsKernelError, match="not an authority"):
        forged.assert_canonical()


def test_physics_registry_digest_cannot_be_relabelled():
    tampered = replace(canonical_physics_v1(), digest="0" * 64)
    with pytest.raises(PhysicsKernelError, match="seal mismatch"):
        tampered.assert_canonical()
