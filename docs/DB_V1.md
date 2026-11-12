# Database authority v1

Status: **one SQLite file per grant, under `ks run`.** `ks build` refuses a
program that uses it (`KS4004`): native binaries are built without cgo and
link no SQLite yet. Implementation: `koschei/db_v1.py`; tests:
`tests/test_db_v1.py`.

```ks
import json

fn main(caps: SystemCaps) {
    let db = caps.db.allow("/srv/app/app.db", 1000, 10485760, 2000)
    let made = db.exec("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT)", "[]") or return
    let added = db.exec("INSERT INTO notes (body) VALUES (?)", json.array([json.string("hi")])) or return
    let rows = db.query("SELECT id, body FROM notes WHERE id > ?", json.array([json.int(0)])) or return
}
```

## Surface

| Expression | Type | Meaning |
|---|---|---|
| `caps.db.allow(path, max_rows, max_bytes, deadline_ms)` | `DbCaps` | static literals: an absolute path without `..`, 1–100000 rows, 65536 bytes–1 GiB, 1–120000 ms (`KS2460`/`KS2461`) |
| `db.exec(sql, params)` | `Int or Error` | runs one statement; the number of rows changed |
| `db.query(sql, params)` | `Data or Error` | runs one statement; a JSON array with one object per row |

`ks caps` names the file and the three budgets; `ks caps --deny db` refuses
the program. The playground and the MCP server deny the domain by default.

## SQL is code, values are data

`sql` must be a string literal. A variable or an interpolated string is
`KS2462` at check time, so no value can become SQL. `params` is the text of
a JSON array, usually built with the `json` module, whose items bind to the
`?` placeholders in order:

| JSON | SQLite |
|---|---|
| integer | INTEGER (64-bit) |
| number with a fraction or exponent | REAL |
| string | TEXT |
| `true` / `false` | 1 / 0 |
| `null` | NULL |

An array or object item, a number outside 64 bits or infinity is `KS3481`.

Rows come back with their SQLite types: INTEGER and REAL are numbers, TEXT a
string, NULL `null`. A BLOB is refused (`KS3480`). `encode_json` writes a row
object with its keys sorted.

## What a statement may do

An authorizer admits reading and writing tables, creating and dropping
tables, indexes, views and triggers, `ALTER TABLE`, transactions and
savepoints, recursive queries and SQL functions. It refuses, as `KS3484`:

- `ATTACH` and `DETACH`, and so `VACUUM INTO`, which would write another file;
- `PRAGMA`;
- virtual tables;
- `load_extension`.

The connection runs with `trusted_schema` off and, where Python's `sqlite3`
offers it, SQLite's defensive mode. The file is created on first use; its
directory must exist. A path that is a symbolic link, or anything but a
regular file, is `KS3485`.

## Budgets

| Budget | Enforced |
|---|---|
| `max_rows` | a query that would return more rows is `KS3482`; nothing is returned |
| `max_bytes` | `PRAGMA max_page_count`; a write that would grow the file past it is `KS3482` and changes nothing |
| `deadline_ms` | a progress handler interrupts the statement (`KS3483`); also the wait for a lock held by another connection |

One call runs one statement: `"SELECT 1; SELECT 2"` is `KS3480`. Statements
run in autocommit mode; `BEGIN` and `COMMIT` group them.

## Not yet

- Native binaries (`KS4004`).
- BLOB columns.
- Streaming results larger than `max_rows`.
