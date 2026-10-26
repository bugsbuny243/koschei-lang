"""Normalize the Structured Task Safety Go helper block.

The safety bridge intentionally patches generated Go after the base structured-task
runtime is installed. Its helper template must contain real indentation characters,
not literal backslash-t escape pairs. Keep this as an explicit fail-closed alignment
layer so a future runtime layout change cannot silently emit invalid Go.
"""

from __future__ import annotations

from . import codegen_go as _codegen

_INSTALLED = False
_START = "func ksTaskArgumentShareSafe(value any) bool {"
_END = "func ksTaskSpawn(scopeValue any, workerValue any, argument any) any {"


def install_structured_task_safety_go_alignment() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    prelude = _codegen.RUNTIME_PRELUDE
    start = prelude.find(_START)
    end = prelude.find(_END, start + len(_START)) if start >= 0 else -1
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(
            "Structured Task Safety Go helper layout changed; alignment failed closed."
        )

    helper = prelude[start:end]
    normalized = helper.replace("\\t", "\t")
    if "\\t" in normalized:
        raise RuntimeError(
            "Structured Task Safety Go helper still contains literal tab escapes."
        )
    if normalized == helper and "\t" not in helper:
        raise RuntimeError(
            "Structured Task Safety Go helper contains no recognizable indentation."
        )

    _codegen.RUNTIME_PRELUDE = prelude[:start] + normalized + prelude[end:]
    _INSTALLED = True
