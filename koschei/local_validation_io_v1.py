"""Strict JSON handoff for CI-independent Koschei validation receipts v1.

A receipt may be produced in Colab/local execution and stored in the Drive
validation vault. Loading it is intentionally strict: unknown/missing fields,
wrong container types, bool-as-int return codes and seal drift all fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_validation_v1 import (
    LocalValidationError,
    LocalValidationReceiptV1,
    LocalValidationStepV1,
)

_STEP_KEYS = frozenset(
    {
        "step_id",
        "command",
        "returncode",
        "stdout_sha256",
        "stderr_sha256",
        "passed",
        "digest",
        "version",
    }
)
_RECEIPT_KEYS = frozenset(
    {
        "source_commit",
        "checkout_clean",
        "profile",
        "python_version",
        "go_version",
        "platform",
        "steps",
        "passed",
        "release_eligible",
        "authority",
        "digest",
        "version",
    }
)


def _require_exact_keys(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    keys = frozenset(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        detail: list[str] = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unknown:
            detail.append("unknown=" + ",".join(unknown))
        raise LocalValidationError(f"invalid {label} fields: {'; '.join(detail)}")


def _parse_step(value: object, index: int) -> LocalValidationStepV1:
    if not isinstance(value, dict):
        raise LocalValidationError(f"validation step {index} must be an object")
    _require_exact_keys(value, _STEP_KEYS, f"validation step {index}")

    command = value["command"]
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise LocalValidationError(f"validation step {index} command must be a non-empty string list")
    returncode = value["returncode"]
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise LocalValidationError(f"validation step {index} returncode must be an integer")
    passed = value["passed"]
    if not isinstance(passed, bool):
        raise LocalValidationError(f"validation step {index} passed must be boolean")
    version = value["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise LocalValidationError(f"validation step {index} version must be an integer")

    try:
        step = LocalValidationStepV1(
            step_id=value["step_id"],
            command=tuple(command),
            returncode=returncode,
            stdout_sha256=value["stdout_sha256"],
            stderr_sha256=value["stderr_sha256"],
            passed=passed,
            digest=value["digest"],
            version=version,
        )
    except TypeError as error:
        raise LocalValidationError(f"invalid validation step {index}: {error}") from error
    step.assert_sealed()
    return step


def parse_local_validation_receipt_v1(value: object) -> LocalValidationReceiptV1:
    """Parse an untrusted JSON-shaped value into one verified receipt."""

    if not isinstance(value, dict):
        raise LocalValidationError("local validation receipt must be an object")
    _require_exact_keys(value, _RECEIPT_KEYS, "local validation receipt")

    steps_value = value["steps"]
    if not isinstance(steps_value, list) or not steps_value:
        raise LocalValidationError("local validation receipt steps must be a non-empty list")
    steps = tuple(_parse_step(step, index) for index, step in enumerate(steps_value))

    checkout_clean = value["checkout_clean"]
    passed = value["passed"]
    release_eligible = value["release_eligible"]
    authority = value["authority"]
    for field, field_value in (
        ("checkout_clean", checkout_clean),
        ("passed", passed),
        ("release_eligible", release_eligible),
        ("authority", authority),
    ):
        if not isinstance(field_value, bool):
            raise LocalValidationError(f"local validation receipt {field} must be boolean")
    version = value["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise LocalValidationError("local validation receipt version must be an integer")

    try:
        receipt = LocalValidationReceiptV1(
            source_commit=value["source_commit"],
            checkout_clean=checkout_clean,
            profile=value["profile"],
            python_version=value["python_version"],
            go_version=value["go_version"],
            platform=value["platform"],
            steps=steps,
            passed=passed,
            release_eligible=release_eligible,
            authority=authority,
            digest=value["digest"],
            version=version,
        )
    except TypeError as error:
        raise LocalValidationError(f"invalid local validation receipt: {error}") from error
    receipt.assert_sealed()
    return receipt


def load_local_validation_receipt_v1(path: str | Path) -> LocalValidationReceiptV1:
    """Load and verify a receipt copied from local/Colab/Drive storage."""

    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LocalValidationError(f"cannot load local validation receipt: {error}") from error
    return parse_local_validation_receipt_v1(raw)
