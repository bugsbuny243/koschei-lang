"""CI-independent validation evidence for Koschei v1.

GitHub-hosted Actions are not an authority boundary for Koschei. Validation may
run locally, in Colab, or on another runner. This module seals the observable
result of that run against the exact source commit and environment facts.

The receipt is evidence only. It never grants execution or deployment authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

_CTX = b"koschei.local-validation/v1\x00"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_PROFILES = frozenset({"core", "full"})


class LocalValidationError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(kind: bytes, value: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(value)).hexdigest()


def _text(value: str, label: str, *, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or "\x00" in value:
        raise LocalValidationError(f"{label} must be non-empty bounded text")
    return value


def _sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value.lower()):
        raise LocalValidationError(f"{label} must be a SHA-256 digest")
    return value.lower()


@dataclass(frozen=True, slots=True)
class LocalValidationStepV1:
    step_id: str
    command: tuple[str, ...]
    returncode: int
    stdout_sha256: str
    stderr_sha256: str
    passed: bool
    digest: str
    version: int = 1

    def _payload(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "passed": self.passed,
        }

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise LocalValidationError("unsupported validation-step version")
        _text(self.step_id, "step_id", limit=96)
        if not self.command:
            raise LocalValidationError("validation step command cannot be empty")
        for index, item in enumerate(self.command):
            _text(item, f"command[{index}]", limit=1024)
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise LocalValidationError("validation step returncode must be an integer")
        _sha256(self.stdout_sha256, "stdout_sha256")
        _sha256(self.stderr_sha256, "stderr_sha256")
        if self.passed is not (self.returncode == 0):
            raise LocalValidationError("validation step pass state disagrees with returncode")
        if self.digest != _hash(b"step", self._payload()):
            raise LocalValidationError("validation step seal mismatch")


@dataclass(frozen=True, slots=True)
class LocalValidationReceiptV1:
    source_commit: str
    checkout_clean: bool
    profile: str
    python_version: str
    go_version: str
    platform: str
    steps: tuple[LocalValidationStepV1, ...]
    passed: bool
    release_eligible: bool
    authority: bool
    digest: str
    version: int = 1

    def _payload(self) -> dict[str, object]:
        return {
            "source_commit": self.source_commit,
            "checkout_clean": self.checkout_clean,
            "profile": self.profile,
            "python_version": self.python_version,
            "go_version": self.go_version,
            "platform": self.platform,
            "steps": [step.digest for step in self.steps],
            "passed": self.passed,
            "release_eligible": self.release_eligible,
            "authority": False,
        }

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise LocalValidationError("unsupported local-validation version")
        if not isinstance(self.source_commit, str) or not _HEX40.fullmatch(self.source_commit.lower()):
            raise LocalValidationError("source_commit must be a 40-character git SHA")
        if not isinstance(self.checkout_clean, bool):
            raise LocalValidationError("checkout_clean must be boolean")
        if self.profile not in _ALLOWED_PROFILES:
            raise LocalValidationError("unsupported local-validation profile")
        _text(self.python_version, "python_version", limit=256)
        _text(self.go_version, "go_version", limit=256)
        _text(self.platform, "platform", limit=256)
        if not self.steps:
            raise LocalValidationError("local validation must contain steps")
        ids: set[str] = set()
        for step in self.steps:
            step.assert_sealed()
            if step.step_id in ids:
                raise LocalValidationError("local validation step IDs must be unique")
            ids.add(step.step_id)
        expected_passed = all(step.passed for step in self.steps)
        if self.passed is not expected_passed:
            raise LocalValidationError("local validation pass state mismatch")
        expected_release = expected_passed and self.checkout_clean and self.profile == "full"
        if self.release_eligible is not expected_release:
            raise LocalValidationError("local validation release eligibility mismatch")
        if self.authority is not False:
            raise LocalValidationError("local validation cannot carry authority")
        if self.digest != _hash(b"receipt", self._payload()):
            raise LocalValidationError("local validation receipt seal mismatch")

    def require_for_release(self, source_commit: str) -> None:
        self.assert_sealed()
        if self.source_commit != source_commit.lower():
            raise LocalValidationError("validation receipt belongs to a different source commit")
        if not self.release_eligible:
            raise LocalValidationError("full clean local validation is required for release")


def seal_local_validation_step_v1(
    *,
    step_id: str,
    command: tuple[str, ...],
    returncode: int,
    stdout_sha256: str,
    stderr_sha256: str,
) -> LocalValidationStepV1:
    result = LocalValidationStepV1(
        step_id=step_id,
        command=command,
        returncode=returncode,
        stdout_sha256=_sha256(stdout_sha256, "stdout_sha256"),
        stderr_sha256=_sha256(stderr_sha256, "stderr_sha256"),
        passed=returncode == 0,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(b"step", result._payload()))
    result.assert_sealed()
    return result


def seal_local_validation_receipt_v1(
    *,
    source_commit: str,
    checkout_clean: bool,
    profile: str,
    python_version: str,
    go_version: str,
    platform: str,
    steps: tuple[LocalValidationStepV1, ...],
) -> LocalValidationReceiptV1:
    normalized_commit = source_commit.lower()
    passed = all(step.passed for step in steps)
    result = LocalValidationReceiptV1(
        source_commit=normalized_commit,
        checkout_clean=checkout_clean,
        profile=profile,
        python_version=python_version,
        go_version=go_version,
        platform=platform,
        steps=steps,
        passed=passed,
        release_eligible=passed and checkout_clean and profile == "full",
        authority=False,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(b"receipt", result._payload()))
    result.assert_sealed()
    return result
