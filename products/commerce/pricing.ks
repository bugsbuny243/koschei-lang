// Koschei Commerce — fixed, bounded cart pricing. Input-only capability.
// Input protocol:
//   CART|1
//   ROW|quantity|unit_price_in_minor_currency_units
// The Python HTTP bridge validates catalog entries and quantities before invoking
// this trusted program; it passes no source code, credentials, names or PII.
// Prices are merchant-entered tax-inclusive prices. No tax invoice is produced.

fn field(parts: List<String>, index: Int) -> String {
    return parts.get(index) or ""
}

fn bounded(raw: String, upper: Int) -> Int or Error {
    let n = raw.to_int() or return Error("invalid number")
    if n < 0 || n > upper {
        return Error("number out of bounds")
    }
    return n
}

fn main(caps: SystemCaps) -> Void or Error {
    let input = caps.input.allow(4096)
    let raw = input.read_text() or return Error("cart missing")
    let lines = raw.split("\n") or return Error("invalid input")
    let start = lines.get(0) or return Error("missing header")
    if start.trim() != "CART|1" {
        return Error("invalid cart version")
    }
    let mut first = true
    let mut count = 0
    let mut quantity_total = 0
    let mut subtotal: Int = 0
    for raw_line in lines {
        if first {
            first = false
            continue
        }
        let line = raw_line.trim()
        if line == "" {
            continue
        }
        let fields = line.split("|") or return Error("invalid row")
        if fields.length() != 3 || field(fields, 0) != "ROW" {
            return Error("invalid row kind")
        }
        let qty = bounded(field(fields, 1), 20) or return
        let unit = bounded(field(fields, 2), 100000000) or return
        if qty == 0 || unit == 0 {
            return Error("zero quantity or price")
        }
        count = count + 1
        if count > 25 {
            return Error("too many cart lines")
        }
        let row = qty * unit
        subtotal = subtotal + row
        quantity_total = quantity_total + qty
    }
    if count == 0 {
        return Error("empty cart")
    }
    println("OK|CART|{subtotal}|{count}|{quantity_total}")
    return
}
