"""Fail-closed local lifecycle supervision for attested Strange native programs.

A sealed memfd launch that is checked only at startup leaves a worker running
after its 120-second epoch expires. This opt-in Linux supervisor polls the
durable Continuity epoch and a monotonic-in-call trusted seconds reader, and
terminates its *own direct process group* at expiry, epoch drift, excessive
output, or bounded runtime expiry.

It is deliberately NOT a sandbox, secure process attestation, signer gate,
multi-node coordinator, or guarantee of instantaneous revocation. A child
can fork, escape its process group, or act between polls. Real secrets must
remain behind a separate, at-effect Trust Plane gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
import signal
import subprocess
import tempfile
import time
from typing import Callable

from .strange_durable_continuity_v1 import (
    StrangeDurableContinuityError,
    StrangeDurableContinuityV1,
)
from .strange_native_admission_v1 import StrangeNativeAttestationV1
from .strange_runtime_observation_v1 import (
    StrangeRuntimeObservationError,
    _verified_seconds,
    require_strange_runtime_observation_v1,
)
from .strange_sealed_native_launch_v1 import (
    StrangeSealedNativeLaunchError,
    _sealed_native_fd,
)


class StrangeSupervisedNativeError(ValueError):
    """Local launch, liveness, or process group supervision failed closed."""


@dataclass(frozen=True, slots=True)
class StrangeSupervisedRunV1:
    """A completed local process observation, NEVER privileged effect authority."""

    exit_code: int
    observed_epoch: int
    native_sha256: str
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    checks: int = 0
    authority: bool = False
    version: int = 1


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate the launched process group; never rely on SIGTERM alone."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        # Some Linux policies deny group signals; fall back to direct child.
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired as exc:
        raise StrangeSupervisedNativeError("unreaped native process") from exc


def run_strange_supervised_native_v1(
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
    run_timeout_seconds: int = 20,
    poll_interval_seconds: float = 0.05,
    max_output_bytes: int = 1_000_000,
) -> StrangeSupervisedRunV1:
    """Run attested sealed bytes while rechecking local Continuity liveness.

    All use of this code must remain within a trusted launcher compartment.
    This cannot prevent a subprocess from making effects before revocation.
    """
    if (
        not isinstance(run_timeout_seconds, int)
        or isinstance(run_timeout_seconds, bool)
        or not 1 <= run_timeout_seconds <= 120
    ):
        raise StrangeSupervisedNativeError("invalid supervised runtime bound")
    if (
        not isinstance(poll_interval_seconds, (float, int))
        or isinstance(poll_interval_seconds, bool)
        or not 0.01 <= poll_interval_seconds <= 0.5
    ):
        raise StrangeSupervisedNativeError("invalid supervision interval")
    if (
        not isinstance(max_output_bytes, int)
        or isinstance(max_output_bytes, bool)
        or not 1 <= max_output_bytes <= 10_000_000
    ):
        raise StrangeSupervisedNativeError("invalid native output limit")
    clock = _verified_seconds(seconds_reader)
    checks = 0
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
        seconds_reader=clock,
        attestation_key=attestation_key,
    )
    try:
        require_strange_runtime_observation_v1(**verify)
    except StrangeRuntimeObservationError as exc:
        raise StrangeSupervisedNativeError("native pre-launch admission rejected") from exc
    try:
        fd = _sealed_native_fd(native_binary)
    except StrangeSealedNativeLaunchError as exc:
        raise StrangeSupervisedNativeError("cannot stage immutable native image") from exc
    try:
        try:
            receipt = require_strange_runtime_observation_v1(**verify)
        except StrangeRuntimeObservationError as exc:
            raise StrangeSupervisedNativeError("native admission expired before exec") from exc
        try:
            now = clock()
            continuity_store.require_active_window(
                expected_epoch=expected_epoch,
                expected_start_seconds=expected_start_seconds,
                observed_seconds=now,
            )
        except (StrangeDurableContinuityError, StrangeRuntimeObservationError) as exc:
            raise StrangeSupervisedNativeError("native admission changed before exec") from exc
        # A local monotonic deadline guards even a stuck/forged seconds reader
        # during this invocation, but it is NOT a durable trusted time source.
        duration = min(run_timeout_seconds, receipt.expires_before_seconds - now)
        if duration <= 0:
            raise StrangeSupervisedNativeError("native epoch window already closed")
        end_monotonic = time.monotonic() + duration
        with tempfile.TemporaryDirectory(prefix="koschei-strange-supervised-") as workspace:
            with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                try:
                    process = subprocess.Popen(
                        [f"/proc/self/fd/{fd}"],
                        cwd=workspace,
                        pass_fds=(fd,),
                        env={
                            "PATH": os.defpath,
                            "LANG": "C",
                            "LC_ALL": "C",
                            "TZ": "UTC",
                        },
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        close_fds=True,
                        start_new_session=True,
                    )
                except OSError as exc:
                    raise StrangeSupervisedNativeError("sealed native spawn rejected") from exc
                try:
                    while True:
                        checks += 1
                        # A new epoch must be rejected even if the local clock
                        # has not yet reached the canonical expiration time.
                        try:
                            tick = clock()
                            continuity_store.require_active_window(
                                expected_epoch=expected_epoch,
                                expected_start_seconds=expected_start_seconds,
                                observed_seconds=tick,
                            )
                        except (StrangeDurableContinuityError, StrangeRuntimeObservationError) as exc:
                            raise StrangeSupervisedNativeError(
                                "native epoch expired or Continuity advanced"
                            ) from exc
                        if time.monotonic() >= end_monotonic:
                            raise StrangeSupervisedNativeError(
                                "native epoch or bounded runtime deadline reached"
                            )
                        if (
                            os.fstat(stdout_file.fileno()).st_size > max_output_bytes
                            or os.fstat(stderr_file.fileno()).st_size > max_output_bytes
                        ):
                            raise StrangeSupervisedNativeError("native output bound exceeded")
                        code = process.poll()
                        if code is not None:
                            # Collect only after the final liveness check; a
                            # late result is not accepted as a current epoch.
                            stdout_file.seek(0)
                            stderr_file.seek(0)
                            return StrangeSupervisedRunV1(
                                exit_code=code,
                                observed_epoch=expected_epoch,
                                native_sha256=hashlib.sha256(native_binary).hexdigest(),
                                stdout=stdout_file.read(max_output_bytes + 1),
                                stderr=stderr_file.read(max_output_bytes + 1),
                                checks=checks,
                            )
                        time.sleep(poll_interval_seconds)
                finally:
                    _terminate_group(process)
    finally:
        os.close(fd)
