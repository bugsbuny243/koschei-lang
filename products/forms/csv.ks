// Koschei Forms: CSV export. Pure.

import text

// One CSV cell: quoted, inner quotes doubled. A cell that a spreadsheet
// would run as a formula (= + - @, tab, carriage return) is prefixed with
// an apostrophe so an exported submission cannot execute in Excel.
fn cell(value: String) -> String {
    let mut safe = value
    if text.starts_with(value, "=") || text.starts_with(value, "+") || text.starts_with(value, "-") || text.starts_with(value, "@") || text.starts_with(value, "\t") || text.starts_with(value, "\r") {
        safe = "'" + value
    }
    let quoted = text.replace(safe, "\"", "\"\"") or safe
    return "\"" + quoted + "\""
}

fn row(cells: List<String>) -> String {
    let mut out: List<String> = []
    for value in cells {
        out = out.push(cell(value))
    }
    return ",".join(out) + "\r\n"
}

// Header: id, received, then every field name in first-seen order.
fn export(rows: Data) -> String or Error {
    let items = json_items(rows) or return Error("csv: rows are not a list")
    let mut names: List<String> = []
    for item in items {
        let fields_text = json_get(item, "fields") or return Error("csv: no fields")
        let raw = json_text(fields_text) or return Error("csv: fields are not text")
        let fields = parse_json(raw) or return Error("csv: fields are not JSON")
        let keys = json_keys(fields) or return Error("csv: fields are not an object")
        for key in keys {
            if !names.contains(key) {
                names = names.push(key)
            }
        }
    }
    let mut header: List<String> = ["id", "received"]
    for name in names {
        header = header.push(name)
    }
    let mut out = row(header)
    for item in items {
        let id_value = json_get(item, "id") or return Error("csv: no id")
        let id = json_int(id_value) or 0
        let when_value = json_get(item, "received") or return Error("csv: no time")
        let when = json_text(when_value) or ""
        let fields_text = json_get(item, "fields") or return Error("csv: no fields")
        let raw = json_text(fields_text) or ""
        let fields = parse_json(raw) or return Error("csv: fields are not JSON")
        let mut cells: List<String> = ["{id}", when]
        for name in names {
            let value = json_get(fields, name) or {
                cells = cells.push("")
                continue
            }
            cells = cells.push(json_text(value) or "")
        }
        out = out + row(cells)
    }
    return out
}
