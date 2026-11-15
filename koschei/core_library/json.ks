// Koschei Core Library: json
//
// Written in Koschei. Builds JSON text from Koschei values. Each function
// returns the encoded text of one JSON value; `array` and `object` take
// values that are already encoded, so documents nest:
//
//     json.object({"name": json.string("Ada"), "tags": json.array([json.int(1)])})
//
// The result is text. Pass it to `parse_json` to get a `Data` value, which also
// checks it: `array` and `object` trust their parts to be encoded JSON.

fn string(value: String) -> String {
    let data = value.to_bytes()
    let mut out = "\"".to_bytes()
    let mut start = 0
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        if b == 34 || b == 92 || b < 32 {
            let plain = data.slice(start, i) or data
            out = out + plain
            out = out + escape(b).to_bytes()
            start = i + 1
        }
        i = i + 1
    }
    let tail = data.slice(start, data.length()) or data
    out = out + tail + "\"".to_bytes()
    return out.to_text() or "\"\""
}

// The escape for one byte that may not appear raw inside a JSON string.
fn escape(b: Int) -> String {
    if b == 34 {
        return "\\\""
    }
    if b == 92 {
        return "\\\\"
    }
    if b == 10 {
        return "\\n"
    }
    if b == 13 {
        return "\\r"
    }
    if b == 9 {
        return "\\t"
    }
    let digits = "0123456789abcdef".to_bytes()
    let high = digits.slice(b / 16, b / 16 + 1) or digits
    let low = digits.slice(b % 16, b % 16 + 1) or digits
    let hex = (high + low).to_text() or "00"
    return "\\u00" + hex
}

fn int(value: Int) -> String {
    return "{value}"
}

// JSON has no infinity or NaN: those are an Error value, never invalid text.
fn float(value: Float) -> String or Error {
    let text = "{value}"
    if text.contains("inf") || text.contains("nan") {
        return Error("json.float: {text} is not a finite number")
    }
    return text
}

fn bool(value: Bool) -> String {
    if value {
        return "true"
    }
    return "false"
}

fn null() -> String {
    return "null"
}

// items: already-encoded JSON values.
fn array(items: List<String>) -> String {
    return "[" + ",".join(items) + "]"
}

// members: names to already-encoded JSON values, written in the map's order.
fn object(members: Map<String, String>) -> String {
    let mut parts: List<String> = []
    for key in members.keys() {
        let value = members.get(key) or "null"
        parts = parts.push(string(key) + ":" + value)
    }
    return "\{" + ",".join(parts) + "\}"
}
