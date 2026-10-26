"""Canonical Koschei-native run/check entrypoints v1.

This module is deliberately narrow.  It accepts only an already authenticated
ObjectSpaceProject.  Filesystem names, source appearance, parser success and
compatibility Program/ModuleGraph carriers are not routing authority here.

The filesystem/crypto admission step stays outside this module so a caller must
first prove Object Space identity, epoch and temporal authority with
load_object_space_project().  Once admitted, canonical check/run cannot fall
back to compatibility execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .native_ir_v1 import NativeIrRealityV1
from .native_value_domains_v1 import NativeValue
from .object_space_native_ir_dispatch_v1 import (
    NativeIrExecutionAuthorityV1,
    lower_authenticated_object_space_to_native_ir_v1,
    execute_authenticated_object_space_native_ir_v1,
)
from .object_space_v1 import ObjectSpaceProject


@dataclass(frozen=True, slots=True)
class CanonicalNativeCheckAuthorityV1:
    """Checked Koschei-native authority with no execution side effect."""

    project_id: bytes
    epoch: int
    ir: NativeIrRealityV1


@dataclass(frozen=True, slots=True)
class CanonicalNativeRunAuthorityV1:
    """Executed Koschei-native authority after authenticated Object Space admission."""

    project_id: bytes
    epoch: int
    execution: NativeIrExecutionAuthorityV1

    @property
    def value(self) -> NativeValue:
        return self.execution.value


def check_canonical_native_v1(project: ObjectSpaceProject) -> CanonicalNativeCheckAuthorityV1:
    """Authenticate semantic dispatch and lower to Native IR without executing it."""

    ir = lower_authenticated_object_space_to_native_ir_v1(project)
    return CanonicalNativeCheckAuthorityV1(
        project_id=project.project_id,
        epoch=project.epoch,
        ir=ir,
    )


def run_canonical_native_v1(project: ObjectSpaceProject) -> CanonicalNativeRunAuthorityV1:
    """Execute only the authenticated Object Space -> Native IR authority path."""

    execution = execute_authenticated_object_space_native_ir_v1(project)
    return CanonicalNativeRunAuthorityV1(
        project_id=project.project_id,
        epoch=project.epoch,
        execution=execution,
    )
