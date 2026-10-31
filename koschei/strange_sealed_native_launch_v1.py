"""Linux-only, sealed-memfd native launch for Strange v1.

Launch from a F_SEAL_WRITE/GROW/SHRINK/SEAL immutable memfd containing exact
bytes checked against a current native attestation. This narrows the on-disk
path-swap gap; it does NOT attest the running host, sandbox the child, enforce
120-second process retirement, or authorize any privileged Galaxy effect.

Only call from a trusted launcher compartment; an untrusted caller can bypass
this Python function entirely. No extra arguments, inherited secrets, or
ambient process environment are forwarded to the child.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import fcntl
import hashlib
import os
import subprocess
import tempfile
from typing import Callable

from .strange_durable_continuity_v1 import StrangeDurableContinuityV1
from .strange_native_admission_v1 import StrangeNativeAttestationV1
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    require_strange_runtime_observation_v1,
)


class StrangeSealedNativeLaunchError(ValueError):
    """Trusted launch observation failed closed."""


_MAX_NATIVE_BYTES = 32 * 1024 * 1024
_REQUIRED_SEALS = (
    fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK
    | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
)


@dataclass(frozen=True, slots=True)
class StrangeSealedNativeRunV1:
    """Read-only local execution observation; never an effect permission."""

    exit_code: int
    native_sha256: str
    epoch_at_launch: int
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    authority: bool = False
    version: int = 1


def _sealed_native_fd(native_binary: bytes) -> int:
    if (
        not isinstance(native_binary, bytes)
        or not 0 < len(native_binary) <= _MAX_NATIVE_BYTES
    ):
        raise StrangeSealedNativeLaunchError("bounded nonempty native binary required")
    if not hasattr(os, "memfd_create") or not os.path.exists("/proc/self/fd"):
        raise StrangeSealedNativeLaunchError("Linux sealed memfd launch unavailable")
    if not hasattr(os, "MFD_ALLOW_SEALING"):
        raise StrangeSealedNativeLaunchError("Linux file sealing unavailable")
    try:
        descriptor = os.memfd_create(
            "koschei-strange-native",
            flags=os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
    except OSError as exc:
        raise StrangeSealedNativeLaunchError("cannot allocate native memfd") from exc
    try:
        view = memoryview(native_binary)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise StrangeSealedNativeLaunchError("short native memfd write")
            written += count
        # Prevent writes, truncation, growth and future seal mutation.
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, _REQUIRED_SEALS)
        if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & _REQUIRED_SEALS != _REQUIRED_SEALS:
            raise StrangeSealedNativeLaunchError("immutable native seal was not applied")
        os.lseek(descriptor, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        count = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            count += len(chunk)
        if (
            count != len(native_binary)
            or digest.hexdigest() != hashlib.sha256(native_binary).hexdigest()
        ):
            raise StrangeSealedNativeLaunchError("memfd differs from verified binary")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def run_strange_sealed_native_v1(
    *,
    continuity_store: StrangeDurableContinuityV1,
    attestation: StrangeNativeAttestationV1,
    native_binary: bytes,
    expected_source_sha256: str,
    deployment_id: str,
    veyra_digest: str,
    mir_fingerprint: str,
    expected_epoch: int,
    expected_start_seconds: int,
    seconds_reader: Callable[[], int],
    attestation_key: bytes,
    timeout_seconds: int = 10,
) -> StrangeSealedNativeRunV1:
    """Validate, copy to an immutable Linux memfd, revalidate and launch.

    Do not pass sensitive data to this process. An already launched process
    may continue past the end of the 120-second representation window.
    """
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 30
    ):
        raise StrangeSealedNativeLaunchError("invalid bounded native run timeout")
    verify = dict(
        continuity_store=continuity_store,
        attestation=attestation,
        native_binary=native_binary,
        expected_source_sha256=expected_source_sha256,
        deployment_id=deployment_id,
        veyra_digest=veyra_digest,
        mir_fingerprint=mir_fingerprint,
        expected_epoch=expected_epoch,
        expected_start_seconds=expected_start_seconds,
        seconds_reader=seconds_reader,
        attestation_key=attestation_key,
    )
    try:
        # Fail before attempting to create an executable if the Trust Plane's
        # current window or the native-byte attestation is incorrect.
        require_strange_runtime_observation_v1(**verify)
    except StrangeRuntimeObservationError as exc:
        raise StrangeSealedNativeLaunchError("pre-launch native admission rejected") from exc
    fd = _sealed_native_fd(native_binary)
    try:
        # Copy and seals may cross an epoch boundary; re-verify immediately
        # before spawning the exact immutable bytes. The residual launch race
        # is a trust-boundary obligation for a native protected supervisor.
        try:
            observation = require_strange_runtime_observation_v1(**verify)
        except StrangeRuntimeObservationError as exc:
            raise StrangeSealedNativeLaunchError(
                "native admission expired during sealed preparation"
            ) from exc
        with tempfile.TemporaryDirectory(prefix="koschei-strange-run-") as workdir:
            try:
                result = subprocess.run(
                    [f"/proc/self/fd/{fd}"],
                    cwd=workdir,
                    pass_fds=(fd,),
                    env={
                        "PATH": os.defpath,
                        "LANG": "C",
                        "LC_ALL": "C",
                        "TZ": "UTC",
                    },
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise StrangeSealedNativeLaunchError(
                    "sealed native process failed or exceeded time bound"
                ) from exc
        return StrangeSealedNativeRunV1(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            native_sha256=hashlib.sha256(native_binary).hexdigest(),
            epoch_at_launch=observation.observed_epoch,
        )
    finally:
        os.close(fd)
