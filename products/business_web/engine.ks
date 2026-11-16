// Koschei Business Web v1 — trusted, fixed-logic calculation engine.
// This program receives ONLY bounded integer data from the website's validated
// HTTP bridge. No uploaded Koschei source is ever interpreted.
// Explicit capability surface: input only; no disk, net, process, env or DB.
// The browser retains item names/descriptions locally; this process sees numbers.

fn value(parts: List<String>, index: Int) -> String {
    return parts.get(index) or ""
}

fn number(text: String, ceiling: Int) -> Int or Error {
    let n = text.to_int() or return Error("invalid integer")
    if n < 0 || n > ceiling {
        return Error("integer outside allowed range")
    }
    return n
}

fn quote(lines: List<String>, header: List<String>) -> Void or Error {
    if header.length() != 3 {
        return Error("invalid quote header")
    }
    let discount = number(value(header, 1), 100) or return
    let vat = number(value(header, 2), 100) or return
    let mut subtotal: Int = 0
    let mut count = 0
    let mut first = true
    for raw in lines {
        if first {
            first = false
            continue
        }
        let line = raw.trim()
        if line == "" {
            continue
        }
        let fields = line.split("|") or return Error("row split")
        if fields.length() != 3 || value(fields, 0) != "ROW" {
            return Error("invalid quote row")
        }
        let qty = number(value(fields, 1), 1000) or return
        let unit = number(value(fields, 2), 100000000) or return
        if qty == 0 {
            return Error("zero quantity")
        }
        count = count + 1
        if count > 24 {
            return Error("too many rows")
        }
        subtotal = subtotal + qty * unit
    }
    if count == 0 {
        return Error("no quote rows")
    }
    let rebate = (subtotal * discount + 50) / 100
    let taxable = subtotal - rebate
    let tax = (taxable * vat + 50) / 100
    let total = taxable + tax
    println("OK|QUOTE|{subtotal}|{rebate}|{tax}|{total}|{count}")
    return
}

fn stock(lines: List<String>, header: List<String>) -> Void or Error {
    if header.length() != 1 {
        return Error("invalid stock header")
    }
    let mut count = 0
    let mut alerts = 0
    let mut inventory: Int = 0
    let mut results: List<String> = []
    let mut first = true
    for raw in lines {
        if first {
            first = false
            continue
        }
        let line = raw.trim()
        if line == "" {
            continue
        }
        let fields = line.split("|") or return Error("stock row split")
        if fields.length() != 4 || value(fields, 0) != "ROW" {
            return Error("invalid stock row")
        }
        let qty = number(value(fields, 1), 100000) or return
        let min_qty = number(value(fields, 2), 100000) or return
        let unit = number(value(fields, 3), 100000000) or return
        count = count + 1
        if count > 40 {
            return Error("too many stock rows")
        }
        inventory = inventory + qty * unit
        if qty <= min_qty {
            let mut reorder = min_qty * 2 - qty
            if reorder <= 0 {
                reorder = 1
            }
            alerts = alerts + 1
            results = results.push("ROW|{count}|LOW|{reorder}")
        } else {
            results = results.push("ROW|{count}|OK|0")
        }
    }
    if count == 0 {
        return Error("no stock rows")
    }
    for result in results {
        println(result)
    }
    println("OK|STOCK|{count}|{alerts}|{inventory}")
    return
}

fn cash(lines: List<String>, header: List<String>) -> Void or Error {
    if header.length() != 2 {
        return Error("invalid cash header")
    }
    let opening = number(value(header, 1), 1000000000000) or return
    let mut income: Int = 0
    let mut expenses: Int = 0
    let mut in_count = 0
    let mut out_count = 0
    let mut first = true
    for raw in lines {
        if first {
            first = false
            continue
        }
        let line = raw.trim()
        if line == "" {
            continue
        }
        let fields = line.split("|") or return Error("cash row split")
        if fields.length() != 2 {
            return Error("invalid cash row")
        }
        let amount = number(value(fields, 1), 100000000000) or return
        if amount == 0 {
            return Error("zero cash amount")
        }
        let kind = value(fields, 0)
        if kind == "IN" {
            income = income + amount
            in_count = in_count + 1
        } else if kind == "OUT" {
            expenses = expenses + amount
            out_count = out_count + 1
        } else {
            return Error("invalid cash kind")
        }
        if in_count + out_count > 40 {
            return Error("too many cash rows")
        }
    }
    if in_count + out_count == 0 {
        return Error("no cash rows")
    }
    let closing = opening + income - expenses
    println("OK|CASH|{opening}|{income}|{expenses}|{closing}|{in_count}|{out_count}")
    return
}

fn main(caps: SystemCaps) -> Void or Error {
    let input = caps.input.allow(8192)
    let body = input.read_text() or return Error("input unreadable")
    let lines = body.split("\n") or return Error("input split")
    let first = lines.get(0) or return Error("missing request")
    let header = first.trim().split("|") or return Error("header split")
    let mode = value(header, 0)
    if mode == "QUOTE" {
        quote(lines, header) or return
    } else if mode == "STOCK" {
        stock(lines, header) or return
    } else if mode == "CASH" {
        cash(lines, header) or return
    } else {
        return Error("unsupported mode")
    }
    return
}
