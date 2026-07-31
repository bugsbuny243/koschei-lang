"""Koschei standard-library capability and implementation contract.

The catalog is deliberately executable data rather than a marketing checklist.
A feature is marked ``supported`` only when the public operation exists in both
bootstrap execution paths used by the repository today: the Python interpreter
and the generated native Go runtime. ``reserved`` means syntax/type surface may
exist, but programs must not rely on the operation yet. ``planned`` names a
roadmap family without pretending that an implementation exists.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Literal, Sequence

SCHEMA = "koschei.stdlib/v1"

OperationStatus = Literal["supported", "reserved", "planned"]
FamilyStatus = Literal["bootstrap", "partial", "planned"]


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    status: OperationStatus
    interpreter: bool = False
    native_go: bool = False
    capability: str | None = None
    budgets: tuple[str, ...] = ()
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
    budgets: tuple[str, ...] = (),
    note: str = "",
) -> Operation:
    return Operation(
        name=name,
        status="supported",
        interpreter=True,
        native_go=True,
        capability=capability,
        budgets=budgets,
        note=note,
    )


def _reserved(
    name: str,
    *,
    capability: str | None = None,
    budgets: tuple[str, ...] = (),
    note: str,
) -> Operation:
    return Operation(
        name=name,
        status="reserved",
        capability=capability,
        budgets=budgets,
        note=note,
    )


def _planned(
    name: str,
    *,
    capability: str | None = None,
    budgets: tuple[str, ...] = (),
    note: str = "",
) -> Operation:
    return Operation(
        name=name,
        status="planned",
        capability=capability,
        budgets=budgets,
        note=note,
    )


CATALOG: tuple[Family, ...] = (
    Family(
        "core",
        "bootstrap",
        "v1",
        "Canonical output and explicit error values.",
        (
            _supported("print", budgets=("output_bytes",)),
            _supported("println", budgets=("output_bytes",)),
            _supported("Error"),
        ),
    ),
    Family(
        "result",
        "bootstrap",
        "v1",
        "Koschei-native fallible values and the single or-handling model.",
        tuple(
            _supported(name)
            for name in ("Some", "None", "Ok", "Err", "or return", "or value", "or block")
        ),
    ),
    Family(
        "text",
        "partial",
        "v1",
        "Unicode text with deterministic, bounded transformations.",
        tuple(
            _supported(name, budgets=("result_bytes",))
            for name in ("length", "to_int", "to_float", "contains", "trim", "split", "join")
        )
        + tuple(
            _planned(name, budgets=("result_bytes",))
            for name in ("starts_with", "ends_with", "replace", "slice", "normalize")
        ),
    ),
    Family(
        "list",
        "partial",
        "v1",
        "Immutable typed sequences that cannot launder capabilities.",
        tuple(
            _supported(name, budgets=("items", "work"))
            for name in ("length", "get", "push", "contains", "sort", "filter")
        )
        + tuple(
            _planned(name, budgets=("items", "work"))
            for name in ("map", "fold", "take", "drop", "first", "last", "find", "concat")
        ),
    ),
    Family(
        "map",
        "partial",
        "v1",
        "Immutable deterministic maps that cannot launder capabilities.",
        tuple(
            _supported(name, budgets=("entries", "work"))
            for name in ("get", "set", "keys", "contains")
        )
        + tuple(
            _planned(name, budgets=("entries", "work"))
            for name in ("length", "values", "entries", "remove", "merge")
        ),
    ),
    Family(
        "data",
        "partial",
        "v1",
        "Bounded deterministic JSON and future schema-guided data codecs.",
        (
            _reserved(
                "parse_json",
                budgets=("input_bytes", "nodes", "depth"),
                note="The semantic name exists in the bootstrap, but interpreter/native execution is not implemented.",
            ),
            _planned("encode_json", budgets=("output_bytes", "nodes", "depth")),
            _planned("validate", budgets=("nodes", "depth", "work")),
        ),
    ),
    Family(
        "request",
        "partial",
        "v1",
        "Origin-scoped outbound HTTP with redirect confinement.",
        (
            _supported(
                "allow",
                capability="NetRoot",
                note="Narrows the root to one HTTP(S) origin.",
            ),
            _supported(
                "get",
                capability="NetCaps",
                budgets=("deadline", "response_bytes", "redirects"),
            ),
            *(
                _reserved(
                    name,
                    capability="NetCaps",
                    budgets=("deadline", "request_bytes", "response_bytes", "redirects"),
                    note="Reserved by the bootstrap API; runtime currently returns unsupported.",
                )
                for name in ("post", "put", "delete", "request")
            ),
        ),
    ),
    Family(
        "serve",
        "planned",
        "v1",
        "Capability-bound HTTP server with request, connection and response budgets.",
        (_planned("listen", capability="ServeCaps", budgets=("connections", "request_bytes", "deadline")),),
    ),
    Family(
        "disk",
        "bootstrap",
        "v1",
        "Descriptor-anchored file access with no symlink traversal or ambient paths.",
        (
            _supported("allow", capability="DiskRoot"),
            _supported("allow_read_only", capability="DiskRoot"),
            *(
                _supported(name, capability="DiskCaps", budgets=("bytes", "entries", "deadline"))
                for name in ("read", "read_file", "write", "write_file", "list", "delete")
            ),
        ),
    ),
    Family(
        "env",
        "bootstrap",
        "v1",
        "Per-name environment access rather than ambient process environment.",
        (
            _supported("allow", capability="EnvRoot"),
            _supported("get", capability="EnvCaps", budgets=("value_bytes",)),
            _planned("secret", capability="EnvCaps", budgets=("value_bytes",), note="Returns a non-printable Secret value."),
        ),
    ),
    Family(
        "process",
        "partial",
        "v2",
        "Shell-free child execution with explicit executable and resource limits.",
        (
            _supported("allow", capability="ProcessRoot"),
            _reserved(
                "run",
                capability="ProcessCaps",
                budgets=("deadline", "cpu", "memory", "output_bytes"),
                note="Runtime is intentionally fail-closed in this version.",
            ),
            _reserved(
                "spawn",
                capability="ProcessCaps",
                budgets=("deadline", "cpu", "memory", "output_bytes", "children"),
                note="Runtime is intentionally fail-closed in this version.",
            ),
        ),
    ),
    Family("clock", "planned", "v1", "Monotonic time, wall time and explicit deadlines.", (_planned("now", capability="ClockCaps"), _planned("deadline", capability="ClockCaps"))),
    Family("log", "planned", "v1", "Structured logs with secret redaction and output budgets.", (_planned("event", capability="LogCaps", budgets=("output_bytes", "events")),)),
    Family("secure", "planned", "v1", "Hashing, signatures and constant-time verification.", (_planned("hash", budgets=("input_bytes", "work")), _planned("verify", budgets=("input_bytes", "work")))),
    Family("random", "planned", "v1", "Cryptographically secure randomness only.", (_planned("bytes", capability="RandomCaps", budgets=("output_bytes",)),)),
    Family("identity", "planned", "v1", "Collision-resistant identifiers with explicit entropy source.", (_planned("new", capability="RandomCaps"),)),
    Family("encode", "planned", "v1", "Bounded UTF-8, hex and base64 codecs.", tuple(_planned(name, budgets=("input_bytes", "output_bytes")) for name in ("utf8", "hex", "base64"))),
    Family("config", "planned", "v1", "Schema-validated configuration assembled only from granted sources.", (_planned("load", capability="ConfigCaps", budgets=("input_bytes", "nodes", "depth")),)),
    Family("database", "planned", "v1", "Query-scoped database capabilities, typed parameters and bounded result sets.", (_planned("query", capability="DatabaseCaps", budgets=("deadline", "rows", "bytes")), _planned("transaction", capability="DatabaseCaps", budgets=("deadline", "statements")))),
    Family("test", "planned", "v1", "Deterministic tests, property checks and capability fakes.", (_planned("case", budgets=("work",)), _planned("property", budgets=("cases", "work")))),
    Family("task", "planned", "v2", "Structured concurrency: child tasks cannot outlive their scope.", (_planned("scope", capability="TaskCaps", budgets=("tasks", "deadline")),)),
    Family("channel", "planned", "v2", "Bounded typed message passing with explicit ownership.", (_planned("bounded", budgets=("messages", "bytes")),)),
    Family("stream", "planned", "v2", "Back-pressure-aware bounded byte and value streams.", (_planned("read", capability="StreamCaps", budgets=("bytes", "deadline")),)),
    Family("tls", "planned", "v2", "Explicit trust roots, protocol floors and certificate policy.", (_planned("client", capability="TlsCaps", budgets=("handshakes", "deadline")),)),
    Family("cache", "planned", "v2", "Size- and time-bounded caches with deterministic eviction policy.", (_planned("bounded", capability="CacheCaps", budgets=("entries", "bytes")),)),
    Family("queue", "planned", "v2", "Capability-scoped jobs with retry and poison-message limits.", (_planned("publish", capability="QueueCaps", budgets=("messages", "bytes")), _planned("consume", capability="QueueCaps", budgets=("messages", "deadline")))),
    Family("metrics", "planned", "v2", "Bounded-cardinality metrics that reject untrusted label explosion.", (_planned("record", capability="MetricsCaps", budgets=("series", "events")),)),
    Family("trace", "planned", "v2", "Distributed tracing with bounded attributes and secret redaction.", (_planned("span", capability="TraceCaps", budgets=("spans", "attributes", "bytes")),)),
    Family("health", "planned", "v2", "Readiness and liveness state without hidden global mutation.", (_planned("report", capability="HealthCaps", budgets=("checks", "deadline")),)),
    Family("compress", "planned", "v2", "Compression with decompression-ratio and output-size defenses.", (_planned("encode", budgets=("input_bytes", "output_bytes", "work")), _planned("decode", budgets=("input_bytes", "output_bytes", "ratio", "work")))),
    Family("dns", "planned", "v2", "Policy-controlled resolution resistant to private-range and rebinding surprises.", (_planned("resolve", capability="DnsCaps", budgets=("answers", "deadline")),)),
    Family("websocket", "planned", "v3", "Connection- and message-bounded bidirectional sessions.", (_planned("connect", capability="WebSocketCaps", budgets=("messages", "bytes", "deadline")),)),
)


def validate_catalog(catalog: Sequence[Family] = CATALOG) -> None:
    family_names: set[str] = set()
    for family in catalog:
        if family.name in family_names:
            raise ValueError(f"duplicate stdlib family: {family.name}")
        family_names.add(family.name)
        operation_names: set[str] = set()
        if not family.operations:
            raise ValueError(f"stdlib family has no operations: {family.name}")
        for operation in family.operations:
            if operation.name in operation_names:
                raise ValueError(f"duplicate operation: {family.name}.{operation.name}")
            operation_names.add(operation.name)
            if operation.status == "supported":
                if not operation.interpreter or not operation.native_go:
                    raise ValueError(
                        f"supported operation lacks backend parity: {family.name}.{operation.name}"
                    )
            elif operation.interpreter or operation.native_go:
                raise ValueError(
                    f"non-supported operation claims backend support: {family.name}.{operation.name}"
                )
            if operation.capability is not None and not operation.capability.endswith(("Root", "Caps")):
                raise ValueError(
                    f"invalid capability name: {family.name}.{operation.name} -> {operation.capability}"
                )


def document(catalog: Sequence[Family] = CATALOG) -> dict[str, object]:
    validate_catalog(catalog)
    operations = [operation for family in catalog for operation in family.operations]
    counts = {
        status: sum(operation.status == status for operation in operations)
        for status in ("supported", "reserved", "planned")
    }
    return {
        "schema": SCHEMA,
        "families": [asdict(family) for family in catalog],
        "summary": {
            "families": len(catalog),
            "operations": len(operations),
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
            f"planned={summary['planned']}"
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
