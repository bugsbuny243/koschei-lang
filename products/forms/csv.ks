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
// Submission i is number i + 1, received at whens[i] with records[i].
fn export(whens: List<String>, records: List<Map<String, String>>) -> String {
    let mut names: List<String> = []
    for fields in records {
        for key in fields.keys() {
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
    let mut i = 0
    while i < records.length() {
        let fields: Map<String, String> = records.get(i) or {
            i = i + 1
            continue
        }
        let when = whens.get(i) or ""
        i = i + 1
        let mut cells: List<String> = ["{i}", when]
        for name in names {
            cells = cells.push(fields.get(name) or "")
        }
        out = out + row(cells)
    }
    return out
}
