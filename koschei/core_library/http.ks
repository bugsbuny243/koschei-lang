// Koschei Core Library: http
//
// Written in Koschei. Reads the parts of a request that `ServeCaps.accept()`
// leaves raw: the request target (`request.path()`, query string included),
// percent-encoded text, query strings and `application/x-www-form-urlencoded`
// bodies, and route patterns such as "/users/:id". It also escapes text for
// HTML. Every function is pure: nothing here touches a socket, so no
// capability is needed, and the program decides when input is interpreted.
//
// Malformed input is an Error value or None, never a guess: a `%` that is not
// followed by two hex digits, or bytes that are not UTF-8 once decoded.

// The path part of a request target: everything before the first `?`.
fn path_of(target: String) -> String {
    let pieces = target.split("?") or return target
    let head = pieces.get(0) or return target
    return head
}

// The query part of a request target, without the `?`; "" when there is none.
fn query_of(target: String) -> String {
    let data = target.to_bytes()
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        if b == 63 {
            let rest = data.slice(i + 1, data.length()) or return ""
            return rest.to_text() or ""
        }
        i = i + 1
    }
    return ""
}

fn is_hex_digit(b: Int) -> Bool {
    return (b >= 48 && b <= 57) || (b >= 65 && b <= 70) || (b >= 97 && b <= 102)
}

// Percent-decoding. With `plus_is_space`, `+` is a space, as in query strings
// and form bodies; in a path it stays `+`.
fn unescape(text: String, plus_is_space: Bool) -> String or Error {
    let data = text.to_bytes()
    let mut hex: List<String> = []
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        if b == 37 {
            let high = data.get(i + 1) or return Error("http.decode: `%` at byte {i} is not followed by two hex digits")
            let low = data.get(i + 2) or return Error("http.decode: `%` at byte {i} is not followed by two hex digits")
            if !is_hex_digit(high) || !is_hex_digit(low) {
                return Error("http.decode: `%` at byte {i} is not followed by two hex digits")
            }
            let pair = data.slice(i + 1, i + 3) or return Error("http.decode: bad escape")
            let digits = pair.to_text() or return Error("http.decode: bad escape")
            hex = hex.push(digits)
            i = i + 3
        } else {
            if b == 43 && plus_is_space {
                hex = hex.push("20")
            } else {
                let one = data.slice(i, i + 1) or return Error("http.decode: bad byte")
                hex = hex.push(one.hex())
            }
            i = i + 1
        }
    }
    let raw = bytes_from_hex("".join(hex)) or return Error("http.decode: bad escape")
    let decoded = raw.to_text() or return Error("http.decode: the decoded bytes are not UTF-8 text")
    return decoded
}

// Decodes a path segment: `%2F` becomes `/`, `+` stays `+`.
fn decode(text: String) -> String or Error {
    let value = unescape(text, false) or return Error("http.decode: not valid percent-encoded UTF-8")
    return value
}

// Decodes a query or form component: `+` is a space.
fn decode_form(text: String) -> String or Error {
    let value = unescape(text, true) or return Error("http.decode_form: not valid percent-encoded UTF-8")
    return value
}

// Names and values of a query string or a form body: "a=1&b=two+words".
// A pair without `=` has the value "". Empty pairs are skipped. When a name
// repeats, the last value wins; the map keeps first-seen order.
fn params(text: String) -> Map<String, String> or Error {
    let mut found: Map<String, String> = {}
    if text.length() == 0 {
        return found
    }
    let pairs = text.split("&") or return Error("http.params: too many pairs")
    for pair in pairs {
        if pair.length() > 0 {
            let parts = pair.split("=") or return Error("http.params: too many pairs")
            let raw_name = parts.get(0) or ""
            let mut raw_value = ""
            if parts.length() > 1 {
                let rest = pair.to_bytes().slice(raw_name.to_bytes().length() + 1, pair.to_bytes().length()) or return Error("http.params: bad pair")
                raw_value = rest.to_text() or return Error("http.params: bad pair")
            }
            let name = decode_form(raw_name) or return Error("http.params: a name is not valid percent-encoded UTF-8")
            let value = decode_form(raw_value) or return Error("http.params: the value of {name} is not valid percent-encoded UTF-8")
            found = found.set(name, value)
        }
    }
    return found
}

// The query parameters of a request target, such as `request.path()`.
fn query(target: String) -> Map<String, String> or Error {
    let found = params(query_of(target)) or return Error("http.query: the query string is not valid")
    return found
}

// The non-empty segments of a path, still encoded: "/a//b/" is ["a", "b"].
fn segments(path: String) -> List<String> {
    let mut out: List<String> = []
    let pieces = path_of(path).split("/") or return out
    for piece in pieces {
        if piece.length() > 0 {
            out = out.push(piece)
        }
    }
    return out
}

// Matches a request target against a pattern such as "/users/:id/posts".
// A segment starting with `:` captures the decoded segment under that name;
// other segments are plain text and must equal the decoded segment. The query string is ignored,
// and so are empty segments, so "/users/" matches "/users". None when the
// target does not match or a segment is not valid percent-encoded UTF-8.
fn route(pattern: String, target: String) -> Option<Map<String, String>> {
    let wanted = segments(pattern)
    let given = segments(target)
    if wanted.length() != given.length() {
        return None()
    }
    let mut captured: Map<String, String> = {}
    let mut i = 0
    while i < wanted.length() {
        let want = wanted.get(i) or return None()
        let raw = given.get(i) or return None()
        let value = decode(raw) or return None()
        let name = after_colon(want)
        if name.length() > 0 {
            captured = captured.set(name, value)
        } else {
            if want != value {
                return None()
            }
        }
        i = i + 1
    }
    return Some(captured)
}

// "id" for ":id"; "" for a literal segment.
fn after_colon(segment: String) -> String {
    let data = segment.to_bytes()
    let first = data.get(0) or return ""
    if first != 58 {
        return ""
    }
    let rest = data.slice(1, data.length()) or return ""
    return rest.to_text() or ""
}

// The cookies of a `Cookie` request header: "sid=abc; theme=dark".
// Values are returned as sent, not decoded. A piece without a name or `=`
// is skipped; when a name repeats, the first value wins, as browsers send
// the most specific cookie first.
fn cookies(header: String) -> Map<String, String> {
    let mut found: Map<String, String> = {}
    let pieces = header.split(";") or return found
    for piece in pieces {
        let pair = piece.trim()
        let parts = pair.split("=") or return found
        if parts.length() > 1 {
            let raw_name = parts.get(0) or ""
            let name = raw_name.trim()
            if name.length() > 0 && !found.contains(name) {
                let data = pair.to_bytes()
                let rest = data.slice(raw_name.to_bytes().length() + 1, data.length()) or return found
                let value = rest.to_text() or return found
                found = found.set(name, value.trim())
            }
        }
    }
    return found
}

// Escapes text for HTML element content and quoted attribute values:
// & < > " and ' become character references.
fn escape_html(text: String) -> String {
    let data = text.to_bytes()
    let mut out = "".to_bytes()
    let mut start = 0
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        let mut entity = ""
        if b == 38 {
            entity = "&amp;"
        } else if b == 60 {
            entity = "&lt;"
        } else if b == 62 {
            entity = "&gt;"
        } else if b == 34 {
            entity = "&quot;"
        } else if b == 39 {
            entity = "&#39;"
        }
        if entity.length() > 0 {
            let plain = data.slice(start, i) or data
            out = out + plain + entity.to_bytes()
            start = i + 1
        }
        i = i + 1
    }
    let tail = data.slice(start, data.length()) or data
    out = out + tail
    return out.to_text() or ""
}
