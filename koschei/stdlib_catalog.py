"""Koschei standard-library security and implementation contract.

This module is executable truth, not a marketing checklist.

`required_budgets` names the resource dimensions an operation must eventually
control. `enforced_budgets` names only limits that are actually enforced in both
bootstrap backends today. A security-sensitive operation cannot be `supported`
until every required budget is enforced.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Literal, Sequence

SCHEMA = "koschei.stdlib/v2"

OperationStatus = Literal["supported", "reserved", "planned"]
FamilyStatus = Literal["bootstrap", "partial", "planned"]


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    status: OperationStatus
    interpreter: bool = False
    native_go: bool = False
    capability: str | None = None
    required_budgets: tuple[str, ...] = ()
    enforced_budgets: tuple[str, ...] = ()
    security_sensitive: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class Family:
    name: str
    status: FamilyStatus
    target: str
    purpose: str
    operations: tuple[Operation, ...]


def _supported(
    name: str,
    *,
    capability: str | None = None,
    required: tuple[str, ...] = (),
    enforced: tuple[str, ...] = (),
    security_sensitive: bool = False,
    note: str = "",
) -> Operation:
    return Operation(
        name=name,
        status="supported",
        interpreter=True,
        native_go=True,
        capability=capability,
        required_budgets=required,
        enforced_budgets=enforced,
        security_sensitive=security_sensitive,
        note=note,
    )


def _reserved(
    name: str,
    *,
    capability: str | None = None,
    required: tuple[str, ...] = (),
    enforced: tuple[str, ...] = (),
    security_sensitive: bool = False,
    note: str,
) -> Operation:
    return Operation(
        name=name,
        status="reserved",
        capability=capability,
        required_budgets=required,
        enforced_budgets=enforced,
        security_sensitive=security_sensitive,
        note=note,
    )


def _planned(
    name: str,
    *,
    capability: str | None = None,
    required: tuple[str, ...] = (),
    security_sensitive: bool = False,
    note: str = "",
) -> Operation:
    return Operation(
        name=name,
        status="planned",
        capability=capability,
        required_budgets=required,
        security_sensitive=security_sensitive,
        note=note,
    )


def _family(
    name: str,
    status: FamilyStatus,
    target: str,
    purpose: str,
    *operations: Operation,
) -> Family:
    return Family(name, status, target, purpose, tuple(operations))


CATALOG: tuple[Family, ...] = (
    _family(
        "core",
        "partial",
        "v1",
        "Canonical output and explicit error values.",
        _reserved(
            "print",
            required=("output_bytes",),
            security_sensitive=True,
            note="Capability values are not yet rejected or identically redacted across both backends.",
        ),
        _reserved(
            "println",
            required=("output_bytes",),
            security_sensitive=True,
            note="Capability values are not yet rejected or identically redacted across both backends.",
        ),
        _supported("Error"),
    ),
    _family(
        "result",
        "bootstrap",
        "v1",
        "Koschei-native fallible values and the single or-handling model.",
        *(
            _supported(name)
            for name in (
                "Some",
                "None",
                "Ok",
                "Err",
                "or return",
                "or value",
                "or block",
            )
        ),
    ),
    _family(
        "text",
        "partial",
        "v1",
        "Unicode text with deterministic transformations.",
        _supported("length"),
        _reserved(
            "to_int",
            required=("input_bytes",),
            security_sensitive=True,
            note="Python bootstrap does not yet enforce signed 64-bit conversion parity.",
        ),
        _supported("to_float"),
        _supported("contains"),
        _supported("trim"),
        _supported("split", required=("result_bytes",)),
        _supported("join", required=("result_bytes",)),
        *(
            _planned(name, required=("result_bytes",))
            for name in ("starts_with", "ends_with", "replace", "slice", "normalize")
        ),
    ),
    _family(
        "list",
        "partial",
        "v1",
        "Immutable sequences that cannot launder capabilities.",
        *(_supported(name) for name in ("length", "get", "push", "contains")),
        _supported("sort", required=("items", "work")),
        _supported("filter", required=("items", "work")),
        *(
            _planned(name, required=("items", "work"))
            for name in ("map", "fold", "take", "drop", "first", "last", "find", "concat")
        ),
    ),
    _family(
        "map",
        "partial",
        "v1",
        "Immutable maps that cannot launder capabilities.",
        *(_supported(name) for name in ("get", "set", "keys", "contains")),
        *(
            _planned(name, required=("entries", "work"))
            for name in ("length", "values", "entries", "remove", "merge")
        ),
    ),
    _family(
        "data",
        "partial",
        "v1",
        "Bounded deterministic JSON and schema-guided data codecs.",
        _reserved(
            "parse_json",
            required=("input_bytes", "nodes", "depth"),
            security_sensitive=True,
            note="Semantic name exists, but bounded interpreter/native execution is not implemented.",
        ),
        _planned(
            "encode_json",
            required=("output_bytes", "nodes", "depth"),
            security_sensitive=True,
        ),
        _planned("validate", required=("nodes", "depth", "work")),
    ),
    _family(
        "request",
        "partial",
        "v1",
        "Origin-scoped outbound HTTP with redirect confinement.",
        _supported("allow", capability="NetRoot"),
        _reserved(
            "get",
            capability="NetCaps",
            required=("deadline", "response_bytes", "redirects"),
            enforced=("deadline", "redirects"),
            security_sensitive=True,
            note="Response body is still read without a hard byte limit in both bootstraps.",
        ),
        *(
            _reserved(
                name,
                capability="NetCaps",
                required=("deadline", "request_bytes", "response_bytes", "redirects"),
                security_sensitive=True,
                note="Reserved API; runtime execution is intentionally unavailable.",
            )
            for name in ("post", "put", "delete", "request")
        ),
    ),
    _family(
        "serve",
        "planned",
        "v1",
        "Capability-bound HTTP server with connection and body budgets.",
        _planned(
            "listen",
            capability="ServeCaps",
            required=("connections", "request_bytes", "response_bytes", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "disk",
        "partial",
        "v1",
        "Descriptor-anchored file access with no symlink traversal or ambient paths.",
        _supported("allow", capability="DiskRoot"),
        _supported("allow_read_only", capability="DiskRoot"),
        *(
            _reserved(
                name,
                capability="DiskCaps",
                required=("bytes", "deadline"),
                security_sensitive=True,
                note="File content is not yet bounded identically in both bootstraps.",
            )
            for name in ("read", "read_file", "write", "write_file")
        ),
        _reserved(
            "list",
            capability="DiskCaps",
            required=("entries", "bytes", "deadline"),
            security_sensitive=True,
            note="Directory entries are fully materialized without an entry/byte cap.",
        ),
        _supported(
            "delete",
            capability="DiskCaps",
            security_sensitive=True,
            note="Descriptor-anchored and symlink rejecting; no payload is materialized.",
        ),
    ),
    _family(
        "env",
        "partial",
        "v1",
        "Per-name environment access rather than ambient process environment.",
        _supported("allow", capability="EnvRoot"),
        _reserved(
            "get",
            capability="EnvCaps",
            required=("value_bytes",),
            security_sensitive=True,
            note="A cross-backend maximum value length is not yet enforced.",
        ),
        _planned(
            "secret",
            capability="EnvCaps",
            required=("value_bytes",),
            security_sensitive=True,
            note="Returns a non-printable Secret value.",
        ),
    ),
    _family(
        "process",
        "partial",
        "v2",
        "Shell-free child execution with explicit executable and resource limits.",
        _supported("allow", capability="ProcessRoot"),
        _reserved(
            "run",
            capability="ProcessCaps",
            required=("deadline", "cpu", "memory", "output_bytes"),
            security_sensitive=True,
            note="Runtime is intentionally fail-closed.",
        ),
        _reserved(
            "spawn",
            capability="ProcessCaps",
            required=("deadline", "cpu", "memory", "output_bytes", "children"),
            security_sensitive=True,
            note="Runtime is intentionally fail-closed.",
        ),
    ),
    _family(
        "clock",
        "planned",
        "v1",
        "Monotonic time, wall time and explicit deadlines.",
        _planned("now", capability="ClockCaps", security_sensitive=True),
        _planned("deadline", capability="ClockCaps", security_sensitive=True),
    ),
    _family(
        "log",
        "planned",
        "v1",
        "Structured logs with secret redaction and output budgets.",
        _planned(
            "event",
            capability="LogCaps",
            required=("output_bytes", "events"),
            security_sensitive=True,
        ),
    ),
    _family(
        "secure",
        "planned",
        "v1",
        "Hashing, signatures and constant-time verification.",
        _planned("hash", required=("input_bytes", "work")),
        _planned("verify", required=("input_bytes", "work")),
    ),
    _family(
        "random",
        "planned",
        "v1",
        "Cryptographically secure randomness only.",
        _planned(
            "bytes",
            capability="RandomCaps",
            required=("output_bytes",),
            security_sensitive=True,
        ),
    ),
    _family(
        "identity",
        "planned",
        "v1",
        "Collision-resistant identifiers with explicit entropy.",
        _planned("new", capability="RandomCaps", security_sensitive=True),
    ),
    _family(
        "encode",
        "planned",
        "v1",
        "Bounded UTF-8, hex and base64 codecs.",
        *(
            _planned(name, required=("input_bytes", "output_bytes"))
            for name in ("utf8", "hex", "base64")
        ),
    ),
    _family(
        "config",
        "planned",
        "v1",
        "Schema-validated configuration assembled from granted sources.",
        _planned(
            "load",
            capability="ConfigCaps",
            required=("input_bytes", "nodes", "depth"),
            security_sensitive=True,
        ),
    ),
    _family(
        "database",
        "planned",
        "v1",
        "Query-scoped database capabilities and bounded results.",
        _planned(
            "query",
            capability="DatabaseCaps",
            required=("deadline", "rows", "bytes"),
            security_sensitive=True,
        ),
        _planned(
            "transaction",
            capability="DatabaseCaps",
            required=("deadline", "statements"),
            security_sensitive=True,
        ),
    ),
    _family(
        "test",
        "planned",
        "v1",
        "Deterministic tests, property checks and capability fakes.",
        _planned("case", required=("work",)),
        _planned("property", required=("cases", "work")),
    ),
    _family(
        "task",
        "planned",
        "v2",
        "Structured concurrency with lexical task lifetime.",
        _planned(
            "scope",
            capability="TaskCaps",
            required=("tasks", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "channel",
        "planned",
        "v2",
        "Bounded typed message passing with explicit ownership.",
        _planned("bounded", required=("messages", "bytes")),
    ),
    _family(
        "stream",
        "planned",
        "v2",
        "Back-pressure-aware bounded byte and value streams.",
        _planned(
            "read",
            capability="StreamCaps",
            required=("bytes", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "tls",
        "planned",
        "v2",
        "Explicit trust roots, protocol floors and certificate policy.",
        _planned(
            "client",
            capability="TlsCaps",
            required=("handshakes", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "cache",
        "planned",
        "v2",
        "Size- and time-bounded caches with deterministic eviction.",
        _planned(
            "bounded",
            capability="CacheCaps",
            required=("entries", "bytes"),
            security_sensitive=True,
        ),
    ),
    _family(
        "queue",
        "planned",
        "v2",
        "Capability-scoped jobs with retry and poison-message limits.",
        _planned(
            "publish",
            capability="QueueCaps",
            required=("messages", "bytes"),
            security_sensitive=True,
        ),
        _planned(
            "consume",
            capability="QueueCaps",
            required=("messages", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "metrics",
        "planned",
        "v2",
        "Bounded-cardinality metrics.",
        _planned(
            "record",
            capability="MetricsCaps",
            required=("series", "events"),
            security_sensitive=True,
        ),
    ),
    _family(
        "trace",
        "planned",
        "v2",
        "Distributed tracing with bounded attributes and redaction.",
        _planned(
            "span",
            capability="TraceCaps",
            required=("spans", "attributes", "bytes"),
            security_sensitive=True,
        ),
    ),
    _family(
        "health",
        "planned",
        "v2",
        "Readiness and liveness state without hidden global mutation.",
        _planned(
            "report",
            capability="HealthCaps",
            required=("checks", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "compress",
        "planned",
        "v2",
        "Compression with ratio and output-size defenses.",
        _planned("encode", required=("input_bytes", "output_bytes", "work")),
        _planned(
            "decode",
            required=("input_bytes", "output_bytes", "ratio", "work"),
            security_sensitive=True,
        ),
    ),
    _family(
        "dns",
        "planned",
        "v2",
        "Policy-controlled resolution resistant to rebinding.",
        _planned(
            "resolve",
            capability="DnsCaps",
            required=("answers", "deadline"),
            security_sensitive=True,
        ),
    ),
    _family(
        "websocket",
        "planned",
        "v3",
        "Connection- and message-bounded bidirectional sessions.",
        _planned(
            "connect",
            capability="WebSocketCaps",
            required=("messages", "bytes", "deadline"),
            security_sensitive=True,
        ),
    ),
)


def validate_catalog(catalog: Sequence[Family] = CATALOG) -> None:
    family_names: set[str] = set()
    for family in catalog:
        if family.name in family_names:
            raise ValueError(f"duplicate stdlib family: {family.name}")
        family_names.add(family.name)
        if not family.operations:
            raise ValueError(f"stdlib family has no operations: {family.name}")

        operation_names: set[str] = set()
        for operation in family.operations:
            identity = f"{family.name}.{operation.name}"
            if operation.name in operation_names:
                raise ValueError(f"duplicate operation: {identity}")
            operation_names.add(operation.name)

            if operation.status == "supported":
                if not operation.interpreter or not operation.native_go:
                    raise ValueError(f"supported operation lacks backend parity: {identity}")
            elif operation.interpreter or operation.native_go:
                raise ValueError(f"non-supported operation claims backend support: {identity}")

            required = set(operation.required_budgets)
            enforced = set(operation.enforced_budgets)
            if not enforced.issubset(required):
                raise ValueError(f"enforced budget was not declared required: {identity}")
            if operation.security_sensitive and operation.status == "supported":
                if required != enforced:
                    missing = ", ".join(sorted(required - enforced)) or "<none>"
                    raise ValueError(
                        f"security-sensitive support lacks enforced budgets: {identity}: {missing}"
                    )

            if operation.capability is not None and not operation.capability.endswith(
                ("Root", "Caps")
            ):
                raise ValueError(
                    f"invalid capability name: {identity} -> {operation.capability}"
                )


def document(catalog: Sequence[Family] = CATALOG) -> dict[str, object]:
    validate_catalog(catalog)
    operations = [operation for family in catalog for operation in family.operations]
    counts = {
        status: sum(operation.status == status for operation in operations)
        for status in ("supported", "reserved", "planned")
    }
    bounded = sum(
        operation.status == "supported"
        and set(operation.required_budgets) == set(operation.enforced_budgets)
        for operation in operations
    )
    return {
        "schema": SCHEMA,
        "families": [asdict(family) for family in catalog],
        "summary": {
            "families": len(catalog),
            "operations": len(operations),
            "fully_bounded_supported": bounded,
            **counts,
        },
    }


def _text_report(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    lines = [
        f"Koschei standard library contract: {payload['schema']}",
        (
            f"families={summary['families']} operations={summary['operations']} "
            f"supported={summary['supported']} reserved={summary['reserved']} "
            f"planned={summary['planned']} "
            f"fully_bounded_supported={summary['fully_bounded_supported']}"
        ),
        "",
    ]
    for family in CATALOG:
        counts = {
            status: sum(operation.status == status for operation in family.operations)
            for status in ("supported", "reserved", "planned")
        }
        lines.append(
            f"{family.name:10} {family.status:9} target={family.target:2} "
            f"supported={counts['supported']:2} reserved={counts['reserved']:2} "
            f"planned={counts['planned']:2}"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ks-stdlib",
        description="Show the machine-checked Koschei standard-library contract.",
    )
    parser.add_argument("--json", action="store_true", help="emit canonical JSON")
    arguments = parser.parse_args(argv)
    payload = document()
    if arguments.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(_text_report(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
