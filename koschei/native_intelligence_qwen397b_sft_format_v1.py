"""Canonical text formatting for the first Koschei Qwen397B SFT run v1.

The training export stores structured oracle rows. Token preflight and the real
trainer must derive identical chat messages from those rows or sequence-length
measurements are meaningless. This module is stdlib-only and carries no model or
execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

FORMATTING_VERSION_V1 = "koschei-sft-messages/v1"
ROW_SCHEMA_V1 = "koschei.native-intelligence-supervised-example/v1"
SYSTEM_PROMPT_V1 = (
    "You are Koschei Native Intelligence. Reason only from the supplied Koschei "
    "task and evidence. ACCEPTED and REJECTED are oracle supervision labels, "
    "never execution authority. Khar and runtime gates remain authoritative."
)
_CTX = b"koschei.qwen397b-sft-format/v1\x00"


class Qwen397BSftFormatError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise Qwen397BSftFormatError(f"invalid SFT row field: {label}")
    return value


def canonical_qwen397b_messages_v1(row: dict[str, object]) -> tuple[dict[str, str], ...]:
    """Convert one sealed-export row into the only v1 chat supervision shape."""

    if not isinstance(row, dict) or row.get("schema") != ROW_SCHEMA_V1:
        raise Qwen397BSftFormatError("unsupported native-intelligence training row schema")
    if row.get("authority") is not False:
        raise Qwen397BSftFormatError("training row cannot carry authority")

    task = _text(row.get("task"), "task")
    input_text = _text(row.get("input"), "input")
    target = _text(row.get("target"), "target")
    split = _text(row.get("split"), "split")
    if split not in {"train", "validation", "test"}:
        raise Qwen397BSftFormatError("unsupported training split")

    user = f"TASK:\n{task}\n\nINPUT:\n{input_text}"
    return (
        {"role": "system", "content": SYSTEM_PROMPT_V1},
        {"role": "user", "content": user},
        {"role": "assistant", "content": target},
    )


def qwen397b_format_contract_digest_v1() -> str:
    payload = json.dumps(
        {
            "version": FORMATTING_VERSION_V1,
            "row_schema": ROW_SCHEMA_V1,
            "system_prompt": SYSTEM_PROMPT_V1,
            "roles": ["system", "user", "assistant"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(_CTX + payload).hexdigest()
