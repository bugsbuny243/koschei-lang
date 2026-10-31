"""Offline prebuild of NEXT epoch native bytes, without execution authority."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .mir import MirGraph
from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_pending_epoch_projection_v1 import (
    PendingStrangeProjectionV1,
    StrangePendingRepresentationError,
    project_next_strange_epoch_go_v1,
)
from .strange_verified_native_build_v1 import (
    StrangeVerifiedNativeBuildError,
    _pinned_go,
)


class StrangePendingNativeBuildError(ValueError):
    """Future native candidate prebuild failed closed."""


@dataclass(frozen=True, slots=True)
class PendingStrangeNativeBuildV1:
    """Builder-only bytes, deliberately NOT an active native attestation."""

    binary: bytes = field(repr=False)
    pending_projection: PendingStrangeProjectionV1
    native_sha256: str
    go_executable_sha256: str
    authority: bool = False
    version: int = 1

    def assert_consistent(self) -> None:
        if (
            self.version != 1 or self.authority is not False
            or not isinstance(self.pending_projection, PendingStrangeProjectionV1)
            or self.pending_projection.authority is not False
            or self.pending_projection.version != 1
            or not isinstance(self.binary, bytes) or not self.binary
            or hashlib.sha256(self.binary).hexdigest() != self.native_sha256
        ):
            raise StrangePendingNativeBuildError("pending native candidate integrity mismatch")


def prebuild_next_strange_native_v1(
    mir: MirGraph,
    *,
    continuity_store: StrangeDurableContinuityV1,
    trust_plane_seed: bytes,
    expected_current_epoch: int,
    expected_current_start_seconds: int,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
    go_executable: str | Path,
    expected_go_sha256: str,
    build_timeout_seconds: int = 90,
) -> PendingStrangeNativeBuildV1:
    """Compile future native bytes offline then recheck the old epoch is live.

    A pinned Go executable is not a full toolchain trust proof. No secrets,
    keys, runtime permissions or native admission statements are returned.
    """
    if (
        not isinstance(build_timeout_seconds, int)
        or isinstance(build_timeout_seconds, bool)
        or not 1 <= build_timeout_seconds <= 120
    ):
        raise StrangePendingNativeBuildError("invalid bounded future build timeout")
    try:
        go = _pinned_go(go_executable, expected_go_sha256)
        source, pending = project_next_strange_epoch_go_v1(
            mir,
            continuity_store=continuity_store,
            trust_plane_seed=trust_plane_seed,
            expected_current_epoch=expected_current_epoch,
            expected_current_start_seconds=expected_current_start_seconds,
            seconds_reader=seconds_reader,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
        )
    except (StrangeVerifiedNativeBuildError, StrangePendingRepresentationError) as exc:
        raise StrangePendingNativeBuildError("future native candidate preflight failed") from exc
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != pending.source_sha256:
        raise StrangePendingNativeBuildError("future Go source fingerprint mismatch")

    with tempfile.TemporaryDirectory(prefix="koschei-strange-future-") as dirname:
        root = Path(dirname)
        (root / "main.go").write_text(source, encoding="utf-8")
        (root / "go.mod").write_text("module koscheistrange\n\ngo 1.21\n", encoding="utf-8")
        (root / "gocache").mkdir()
        (root / "gotmp").mkdir()
        target = root / "native-program"
        env = {
            "PATH": str(go.parent) + os.pathsep + os.defpath,
            "HOME": str(root),
            "GOCACHE": str(root / "gocache"),
            "GOTMPDIR": str(root / "gotmp"),
            "GOTOOLCHAIN": "local",
            "GOWORK": "off",
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "CGO_ENABLED": "0",
            "GOFLAGS": "",
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
        }
        try:
            completed = subprocess.run(
                [str(go), "build", "-trimpath", "-buildvcs=false",
                 "-ldflags=-buildid=", "-o", str(target), "."],
                cwd=root,
                env=env,
                capture_output=True,
                timeout=build_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StrangePendingNativeBuildError("future native offline build failed closed") from exc
        if completed.returncode != 0 or not target.is_file() or target.is_symlink():
            raise StrangePendingNativeBuildError("future native offline build failed closed")
        data = target.read_bytes()
        if not data or len(data) > 32 * 1024 * 1024:
            raise StrangePendingNativeBuildError("future native binary size rejected")
    # A slow build crossing the old epoch boundary must discard its output.
    try:
        continuity_store.require_active_window(
            expected_epoch=expected_current_epoch,
            expected_start_seconds=expected_current_start_seconds,
            observed_seconds=seconds_reader(),
        )
    except Exception as exc:
        raise StrangePendingNativeBuildError("old Continuity window ended during prebuild") from exc
    result = PendingStrangeNativeBuildV1(
        binary=data,
        pending_projection=pending,
        native_sha256=hashlib.sha256(data).hexdigest(),
        go_executable_sha256=expected_go_sha256,
    )
    result.assert_consistent()
    return result
