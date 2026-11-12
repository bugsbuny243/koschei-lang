"""Database authority v1: one SQLite file, parameterized statements only.

A program reaches a database only through a narrowed capability::

    import json

    fn main(caps: SystemCaps) {
        let db = caps.db.allow("/srv/app/app.db", 1000, 10485760, 2000)
        let made = db.exec("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT)", "[]") or return
        let added = db.exec("INSERT INTO notes (body) VALUES (?)", json.array([json.string("hi")])) or return
        let rows = db.query("SELECT id, body FROM notes WHERE id > ?", json.array([json.int(0)])) or return
    }

``caps.db.allow(path, max_rows, max_bytes, deadline_ms)`` takes static
literals: an absolute path to the database file, the most rows one query may
return, the largest the file may grow and the time one statement may run. The
file is created on first use; its directory must exist.

**SQL is code, values are data.** The first argument of ``exec`` and ``query``
must be a string literal: a statement built from text at run time is
``KS2462`` at check time, so a value can never become SQL. Values travel as a
JSON array in the second argument (``json.array([...])``) and bind to ``?``
placeholders: Int, Float, String, Bool (1 or 0) and null.

``exec`` returns the number of rows changed; ``query`` returns ``Data``, a JSON
array with one object per row, read with ``json_get`` and friends. Columns keep
their SQLite type: INTEGER and REAL are numbers, TEXT a string, NULL null; a
BLOB is refused.

Every statement runs under an authorizer that admits reading and writing
tables, indexes, views, triggers and transactions, and refuses ``ATTACH``
(which ``VACUUM INTO`` uses), ``DETACH``, ``PRAGMA``, virtual tables and
``load_extension``: a statement can reach this one file and nothing else. The
file cannot grow past ``max_bytes`` (``PRAGMA max_page_count``), a statement
is interrupted at ``deadline_ms`` and a query that would return more than
``max_rows`` rows is refused, each as an Error value.

Native binaries refuse this capability (``KS4004``): they are built without
cgo, and no SQLite is linked into them yet.
"""

from __future__ import annotations

import math
import os
import sqlite3
import stat
import time
from typing import Any

from . import capabilities as _caps
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import mir_executor_v1 as _mir_executor
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import _typed_expr
from . import _typed_ops
from .ast_nodes import Literal, MemberExpression
from .data_json_v1 import DataError, Number, canonical_number, decode
from .data_language_v1 import DataValue
from .type_system import ERROR, INT, NamedType, union_type

MAX_ROWS = 100_000
MIN_BYTES = 65_536
MAX_BYTES = 1 << 30
MIN_DEADLINE_MS = 1
MAX_DEADLINE_MS = 120_000
MAX_PATH_BYTES = 4096

DATA = NamedType("Data")

ALLOW_SHAPE_MESSAGE = (
    "KS2460: caps.db.allow() statik bir mutlak yol ve üç statik Int bekler: "
    "max_rows, max_bytes, deadline_ms."
)
ALLOW_RANGE_MESSAGE = (
    f"KS2461: caps.db.allow(): yol mutlak olmalı ve '..' içermemeli; max_rows 1..{MAX_ROWS}, "
    f"max_bytes {MIN_BYTES}..{MAX_BYTES}, deadline_ms {MIN_DEADLINE_MS}..{MAX_DEADLINE_MS}."
)
SQL_LITERAL_MESSAGE = (
    "KS2462: SQL bir metin literali olmalıdır; değerleri metne gömmeyin, '?' ile "
    "parametre olarak verin."
)
STATEMENT_MESSAGE = "KS3480: SQL deyimi çalıştırılamadı: {detail}"
PARAMS_MESSAGE = (
    "KS3481: SQL parametreleri bir JSON dizisi olmalıdır; her öğe Int, Float, String, "
    "Bool veya null."
)
ROWS_MESSAGE = "KS3482: Sorgu en fazla {max_rows} satır döndürebilir."
FULL_MESSAGE = "KS3482: Veritabanı dosyası en fazla {max_bytes} bayt olabilir."
DEADLINE_MESSAGE = "KS3483: SQL deyimi {deadline_ms} ms içinde bitmedi."
DENIED_MESSAGE = (
    "KS3484: Bu SQL işlemine izin yok: ATTACH, DETACH, PRAGMA, sanal tablolar ve "
    "eklenti yükleme kapalıdır."
)
BLOB_MESSAGE = "KS3480: BLOB sütunları v1'de okunamaz."
OPEN_MESSAGE = "KS3485: Veritabanı dosyası açılamadı: {detail}"

# What a statement may do (sqlite3 authorizer action codes).
_ALLOWED_ACTIONS = frozenset(
    getattr(sqlite3, name)
    for name in (
        "SQLITE_CREATE_INDEX", "SQLITE_CREATE_TABLE", "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE", "SQLITE_CREATE_TEMP_TRIGGER", "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER", "SQLITE_CREATE_VIEW", "SQLITE_DELETE", "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE", "SQLITE_DROP_TEMP_INDEX", "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER", "SQLITE_DROP_TEMP_VIEW", "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW", "SQLITE_INSERT", "SQLITE_READ", "SQLITE_SELECT",
        "SQLITE_TRANSACTION", "SQLITE_UPDATE", "SQLITE_ALTER_TABLE", "SQLITE_REINDEX",
        "SQLITE_ANALYZE", "SQLITE_FUNCTION", "SQLITE_SAVEPOINT", "SQLITE_RECURSIVE",
    )
)
_DENIED_FUNCTIONS = frozenset({"load_extension"})

_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_VALIDATE = None
_ORIGINAL_MEMBER = None
_ORIGINAL_METHOD_TYPE = None


def valid_path(path: Any) -> bool:
    return (
        isinstance(path, str)
        and path.startswith("/")
        and 1 < len(path.encode("utf-8", "surrogatepass")) <= MAX_PATH_BYTES
        and "\x00" not in path
        and ".." not in path.split("/")
        and not path.endswith("/")
    )


def _policy_ok(path: Any, max_rows: Any, max_bytes: Any, deadline_ms: Any) -> bool:
    return (
        valid_path(path)
        and type(max_rows) is int and 1 <= max_rows <= MAX_ROWS
        and type(max_bytes) is int and MIN_BYTES <= max_bytes <= MAX_BYTES
        and type(deadline_ms) is int and MIN_DEADLINE_MS <= deadline_ms <= MAX_DEADLINE_MS
    )


# ---- values ------------------------------------------------------------------


def _parameters(text: Any) -> list[Any] | None:
    if not isinstance(text, str):
        return None
    try:
        value = decode(text)
    except DataError:
        return None
    if not isinstance(value, list):
        return None
    out: list[Any] = []
    for item in value:
        if item is None or isinstance(item, str):
            out.append(item)
        elif isinstance(item, bool):
            out.append(1 if item else 0)
        elif isinstance(item, Number):
            number = item.text
            if any(mark in number for mark in ".eE"):
                converted = float(number)
                if not math.isfinite(converted):
                    return None
                out.append(converted)
            else:
                integer = int(number)
                if not -(1 << 63) <= integer < (1 << 63):
                    return None
                out.append(integer)
        else:
            return None
    return out


def _cell(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return Number(canonical_number(str(int(value))))
    if isinstance(value, int):
        return Number(canonical_number(str(value)))
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return Number(canonical_number(repr(value)))
    raise TypeError("blob")


# ---- runtime authority ---------------------------------------------------------


class DbRoot(_runtime._NarrowedCapability):
    __slots__ = ()

    def allow(self, path: Any, max_rows: Any, max_bytes: Any, deadline_ms: Any) -> "DbCaps | _runtime.KsError":
        if not _policy_ok(path, max_rows, max_bytes, deadline_ms):
            return _runtime.KsError(ALLOW_RANGE_MESSAGE)
        return DbCaps(path, max_rows, max_bytes, deadline_ms)


class DbCaps(_runtime._NarrowedCapability):
    __slots__ = ("path", "max_rows", "max_bytes", "deadline_ms", "_connection")

    def __init__(self, path: str, max_rows: int, max_bytes: int, deadline_ms: int) -> None:
        self.path = path
        self.max_rows = max_rows
        self.max_bytes = max_bytes
        self.deadline_ms = deadline_ms
        self._connection: sqlite3.Connection | None = None

    def __del__(self) -> None:
        connection = getattr(self, "_connection", None)
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def _open(self) -> sqlite3.Connection | _runtime.KsError:
        if self._connection is not None:
            return self._connection
        try:
            existing = os.lstat(self.path)
        except FileNotFoundError:
            existing = None
        except OSError as error:
            return _runtime.KsError(OPEN_MESSAGE.format(detail=error.strerror or "OS error"))
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            return _runtime.KsError(OPEN_MESSAGE.format(detail="not a regular file"))
        try:
            connection = sqlite3.connect(
                self.path, timeout=self.deadline_ms / 1000.0, isolation_level=None,
                check_same_thread=False,
            )
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            connection.execute(f"PRAGMA max_page_count = {max(1, self.max_bytes // page_size)}")
            connection.execute("PRAGMA trusted_schema = OFF")
            if hasattr(connection, "setconfig") and hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE"):
                connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        except sqlite3.Error as error:
            return _runtime.KsError(OPEN_MESSAGE.format(detail=str(error)))
        connection.set_authorizer(_authorize)
        self._connection = connection
        return connection

    def _run(self, sql: Any, params: Any, want_rows: bool):
        if not isinstance(sql, str):
            return _runtime.KsError(SQL_LITERAL_MESSAGE)
        values = _parameters(params)
        if values is None:
            return _runtime.KsError(PARAMS_MESSAGE)
        connection = self._open()
        if isinstance(connection, _runtime.KsError):
            return connection
        deadline = time.monotonic() + self.deadline_ms / 1000.0
        timed_out = [False]

        def progress() -> int:
            if time.monotonic() > deadline:
                timed_out[0] = True
                return 1
            return 0

        connection.set_progress_handler(progress, 1000)
        try:
            cursor = connection.execute(sql, values)
            if not want_rows:
                return cursor.rowcount if cursor.rowcount >= 0 else 0
            names = [column[0] for column in cursor.description or ()]
            fetched = cursor.fetchmany(self.max_rows + 1)
            if len(fetched) > self.max_rows:
                return _runtime.KsError(ROWS_MESSAGE.format(max_rows=self.max_rows))
            rows = []
            for row in fetched:
                record: dict[str, Any] = {}
                for name, value in zip(names, row):
                    try:
                        record[name] = _cell(value)
                    except TypeError:
                        return _runtime.KsError(BLOB_MESSAGE)
                rows.append(record)
            return DataValue(rows)
        except sqlite3.DatabaseError as error:
            text = str(error)
            if timed_out[0] or text == "interrupted":
                return _runtime.KsError(DEADLINE_MESSAGE.format(deadline_ms=self.deadline_ms))
            if "not authorized" in text or "authorization denied" in text:
                return _runtime.KsError(DENIED_MESSAGE)
            if isinstance(error, sqlite3.OperationalError) and "full" in text:
                return _runtime.KsError(FULL_MESSAGE.format(max_bytes=self.max_bytes))
            return _runtime.KsError(STATEMENT_MESSAGE.format(detail=text))
        except (sqlite3.Error, ValueError, OverflowError) as error:
            return _runtime.KsError(STATEMENT_MESSAGE.format(detail=str(error)))
        finally:
            connection.set_progress_handler(None, 0)

    def exec(self, sql: Any, params: Any) -> int | _runtime.KsError:
        return self._run(sql, params, False)

    def query(self, sql: Any, params: Any):
        return self._run(sql, params, True)


def _authorize(action: int, first: Any, second: Any, database: Any, trigger: Any) -> int:
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and isinstance(second, str) and second.lower() in _DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    if database not in (None, "main", "temp"):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


_BaseSystemCaps = _runtime.SystemCaps


class SystemCaps(_BaseSystemCaps):
    __slots__ = ("db",)

    def __init__(self) -> None:
        super().__init__()
        self.db = DbRoot()


_EDGES = {DbRoot: {"allow"}, DbCaps: {"exec", "query"}}


def _member(self, receiver, name, location):
    if isinstance(receiver, SystemCaps) and name == "db":
        return receiver.db
    for receiver_type, names in _EDGES.items():
        if isinstance(receiver, receiver_type) and name in names:
            return _runtime._BoundMember(receiver, name, location)
    return _ORIGINAL_MEMBER(self, receiver, name, location)


# ---- checking --------------------------------------------------------------------


def _literal(expression: Any, kind: type) -> Any:
    if isinstance(expression, Literal) and type(expression.value) is kind:
        return expression.value
    return None


def static_policy(arguments) -> tuple[str, int, int, int] | None:
    if len(arguments) != 4:
        return None
    path = _literal(arguments[0], str)
    numbers = [_literal(argument, int) for argument in arguments[1:]]
    if path is None or any(number is None for number in numbers):
        return None
    return (path, *numbers)  # type: ignore[return-value]


def _check_method_call(self, receiver_type, method_name, location, argument_types=None, arguments=None):
    values = argument_types or []
    if receiver_type == "DbRoot":
        if method_name != "allow":
            raise _semantic.SemanticError(
                "KS2402", "DbRoot doğrudan kullanılamaz; önce caps.db.allow() ile daraltın.", location
            )
        policy = static_policy(arguments or [])
        if len(values) != 4 or policy is None:
            raise _semantic.SemanticError("KS2460", ALLOW_SHAPE_MESSAGE[8:], location)
        if not _policy_ok(*policy):
            raise _semantic.SemanticError("KS2461", ALLOW_RANGE_MESSAGE[8:], location)
        self.capability_count += 1
        return "DbCaps"
    if receiver_type == "DbCaps":
        if method_name in _semantic.NARROWING_METHODS:
            raise _semantic.SemanticError(
                "KS2403", "DbCaps daraltılmış bir yetkidir; yeniden genişletilemez.", location
            )
        if method_name not in {"exec", "query"}:
            raise _semantic.SemanticError(
                "KS2404", f"DbCaps yetkisi '{method_name}' işlemine izin vermez.", location
            )
        if len(values) != 2:
            raise _semantic.SemanticError(
                "KS1301", f"DbCaps.{method_name}() 2 argüman bekler, {len(values)} verildi.", location
            )
        if _literal((arguments or [None])[0], str) is None:
            raise _semantic.SemanticError("KS2462", SQL_LITERAL_MESSAGE[8:], location)
        self._require_assignable(("String",), values[1], f"DbCaps.{method_name}() parametreleri", location)
        return "Int or Error" if method_name == "exec" else "Data or Error"
    return _ORIGINAL_CHECK_METHOD_CALL(self, receiver_type, method_name, location, argument_types, arguments)


_TYPED_RESULTS = {
    ("DbCaps", "exec"): (2, union_type(INT, ERROR)),
    ("DbCaps", "query"): (2, union_type(DATA, ERROR)),
}


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType):
        typed = _TYPED_RESULTS.get((receiver.name, method))
        if typed is not None:
            expected, result = typed
            if len(arguments) != expected:
                raise _semantic.SemanticError(
                    "KS1301", f"{receiver.name}.{method}() {expected} argüman bekler, {len(arguments)} verildi.", location
                )
            return result
    return _ORIGINAL_METHOD_TYPE(receiver, method, arguments, location)


def manifest_scope(arguments) -> str:
    policy = static_policy(arguments)
    if policy is None:
        return _caps.DYNAMIC
    path, max_rows, max_bytes, deadline_ms = policy
    return f"{path} | max_rows={max_rows} | max_bytes={max_bytes} | deadline_ms={deadline_ms}"


def _runtime_type_node(value):
    if isinstance(value, DbRoot):
        return NamedType("DbRoot")
    if isinstance(value, DbCaps):
        return NamedType("DbCaps")
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _validate_capability_backend(self) -> None:
    for declaration in self.program.declarations:
        for parameter in declaration.parameters:
            if any(name in {"DbRoot", "DbCaps"} for name in parameter.type_ref.names):
                raise _codegen.CodegenError(
                    "KS4001", "Veritabanı yetkisi eski AST-Go backend'inde yok.", parameter.location
                )
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member == "db":
                    raise _codegen.CodegenError(
                        "KS4001", "Veritabanı yetkisi eski AST-Go backend'inde yok.", expression.location
                    )
    return _ORIGINAL_CODEGEN_VALIDATE(self)


def install_db_v1() -> None:
    global _INSTALLED, _ORIGINAL_CHECK_METHOD_CALL, _ORIGINAL_RUNTIME_TYPE_NODE
    global _ORIGINAL_CODEGEN_VALIDATE, _ORIGINAL_MEMBER, _ORIGINAL_METHOD_TYPE
    if _INSTALLED:
        return
    _runtime.DbRoot = DbRoot
    _runtime.DbCaps = DbCaps
    _runtime.SystemCaps = SystemCaps
    _mir_executor.SystemCaps = SystemCaps

    _ORIGINAL_MEMBER = _runtime.Interpreter._member
    _runtime.Interpreter._member = _member
    _ORIGINAL_CHECK_METHOD_CALL = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call
    _ORIGINAL_METHOD_TYPE = _typed_ops.method_type
    _typed_ops.method_type = _method_type
    _typed_expr.method_type = _method_type
    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node
    _ORIGINAL_CODEGEN_VALIDATE = _codegen.GoCodegen._validate_capability_backend
    _codegen.GoCodegen._validate_capability_backend = _validate_capability_backend
    _INSTALLED = True


__all__ = ["DbCaps", "DbRoot", "install_db_v1", "manifest_scope", "static_policy", "valid_path"]
