"""Fail-closed, builder-side native provenance checkpoint for sealed Koschei MIR.

An issuer must not MAC an arbitrary native executable and call it a Koschei
build. This opt-in bootstrap derives the actual Go source from sealed MIR,
verifies a caller-pinned Go executable hash, builds the supplied source in an
offline temporary workspace, and only then issues exact-byte native evidence.

This proves neither the rest of the Go toolchain/standard library nor the
hardware clock, private Trust Plane, and independent build reviewer. The
attestation is NEVER a privileged execution or secret-release authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .continuity_epoch_authority_v1 import ContinuityEpochAuthorityV1
from .mir import MirGraph
from .strange_native_admission_v1 import (
    StrangeNativeAttestationV1,
    issue_strange_native_attestation_v1,
)
from .strange_representation_epoch_v1 import (
    StrangeEpochProjectionV1,
    StrangeRepresentationEpochError,
    project_strange_epoch_go_v1,
    require_strange_epoch_window_v1,
)


class StrangeVerifiedNativeBuildError(ValueError):
    """The native build or its evidence failed closed."""


@dataclass(frozen=True, slots=True)
class StrangeVerifiedNativeBuildV1:
    """Trusted-builder artifact. Never serialize native bytes to observers."""

    binary: bytes = field(repr=False)
    projection: StrangeEpochProjectionV1
    attestation: StrangeNativeAttestationV1
    go_executable_sha256: str
    authority: bool = False
    version: int = 1


def _hex256(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise StrangeVerifiedNativeBuildError("canonical pinned Go executable SHA256 required")
    return value


def _pinned_go(executable: str | Path, pinned_sha256: str) -> Path:
    expected = _hex256(pinned_sha256)
    try:
        path = Path(executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise StrangeVerifiedNativeBuildError("absolute executable Go path required")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, TypeError, ValueError) as exc:
        raise StrangeVerifiedNativeBuildError("cannot attest pinned Go executable") from exc
    if actual != expected:
        raise StrangeVerifiedNativeBuildError("Go executable differs from pinned hash")
    return path


def verified_strange_native_build_v1(
    mir: MirGraph,
    *,
    trust_plane_seed: bytes,
    continuity: ContinuityEpochAuthorityV1,
    expected_epoch: int,
    starts_at_seconds: int,
    seconds_reader: Callable[[], int],
    deployment_id: str,
    veyra_digest: str,
    attestation_key: bytes,
    go_executable: str | Path,
    expected_go_sha256: str,
    build_timeout_seconds: int = 90,
) -> StrangeVerifiedNativeBuildV1:
    """Build sealed MIR inside a restricted offline workspace, then attest.

    Trust-plane key custody and clock provenance are external obligations.
    The Go executable pin alone does NOT pin all linked compiler components.
    A pinned compiler can still compile malicious semantics if the trusted
    canonical compiler, sealed MIR, or underlying host are compromised.
    """
    if (
        not isinstance(build_timeout_seconds, int)
        or isinstance(build_timeout_seconds, bool)
        or not 1 <= build_timeout_seconds <= 120
    ):
        raise StrangeVerifiedNativeBuildError("invalid bounded build timeout")
    go = _pinned_go(go_executable, expected_go_sha256)
    try:
        source, receipt = project_strange_epoch_go_v1(
            mir,
            trust_plane_seed=trust_plane_seed,
            continuity=continuity,
            expected_epoch=expected_epoch,
            starts_at_seconds=starts_at_seconds,
            seconds_reader=seconds_reader,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
        )
    except (ValueError, TypeError) as exc:
        raise StrangeVerifiedNativeBuildError("sealed MIR projection rejected") from exc
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != receipt.source_sha256:
        raise StrangeVerifiedNativeBuildError("Go source did not match sealed projection")

    with tempfile.TemporaryDirectory(prefix="koschei-strange-native-build-") as workspace:
        root = Path(workspace)
        (root / "main.go").write_text(source, encoding="utf-8")
        (root / "go.mod").write_text(
            "module koscheistrange\n\ngo 1.21\n", encoding="utf-8"
        )
        (root / "gocache").mkdir()
        (root / "gotmp").mkdir()
        target = root / "native-program"
        # Explicitly disallow ambient module downloads, cgo compiler injection,
        # workspaces and ambient Go flags. Fresh paths are removed at return.
        environment = {
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
                [
                    str(go), "build", "-trimpath", "-buildvcs=false",
                    "-ldflags=-buildid=", "-o", str(target), ".",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                timeout=build_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StrangeVerifiedNativeBuildError("offline native Go build failed closed") from exc
        if completed.returncode != 0 or not target.is_file() or target.is_symlink():
            raise StrangeVerifiedNativeBuildError(
                "offline native Go build failed closed"
            )
        native_binary = target.read_bytes()
        if not native_binary:
            raise StrangeVerifiedNativeBuildError("native build produced empty artifact")

    # A build that crosses the admission window is discarded even if the Go
    # compiler itself completed successfully.
    try:
        require_strange_epoch_window_v1(
            continuity=continuity,
            expected_epoch=expected_epoch,
            starts_at_seconds=starts_at_seconds,
            seconds_reader=seconds_reader,
        )
        proof = issue_strange_native_attestation_v1(
            receipt=receipt,
            native_binary=native_binary,
            deployment_id=deployment_id,
            veyra_digest=veyra_digest,
            mir_fingerprint=mir.fingerprint,
            continuity=continuity,
            expected_epoch=expected_epoch,
            starts_at_seconds=starts_at_seconds,
            seconds_reader=seconds_reader,
            attestation_key=attestation_key,
        )
    except (ValueError, TypeError) as exc:
        raise StrangeVerifiedNativeBuildError("post-build epoch or attestation rejected") from exc
    return StrangeVerifiedNativeBuildV1(
        binary=native_binary,
        projection=receipt,
        attestation=proof,
        go_executable_sha256=expected_go_sha256,
    )
