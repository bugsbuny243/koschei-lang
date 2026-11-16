// Koschei Forms: storage. Pure: no capability reaches this module.
//
// Everything lives as small files in one directory, the disk scope that
// `main.ks` grants. Names carry the keys, so a listing is the index:
//
//   form_<slug>                       content: the redirect URL ("" for none)
//   sub_<slug>_<ms>_<random>          content: the kept fields, form-encoded
//   session_<digest>                  content: expiry, UTC milliseconds
//   fail_<ms>_<random>                content: "1", one failed sign-in
//
// A slug is lowercase letters, digits and '-' (rules.valid_slug), so '_'
// always ends it. Times are zero-padded to 13 digits, so names sort by time.

import text

fn hex_digit(value: Int) -> String {
    let digits = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C", "D", "E", "F"]
    return digits.get(value) or "0"
}

// Percent-encoding of every byte except A-Z a-z 0-9 - . _ ~, so the text
// reads back through http.params unchanged, '+' and spaces included.
fn encode(value: String) -> String {
    let data = value.to_bytes()
    let mut out = ""
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        let upper = b >= 65 && b <= 90
        let lower = b >= 97 && b <= 122
        let digit = b >= 48 && b <= 57
        if upper || lower || digit || b == 45 || b == 46 || b == 95 || b == 126 {
            let one = data.slice(i, i + 1) or data
            out = out + (one.to_text() or "")
        } else {
            out = out + "%" + hex_digit(b / 16) + hex_digit(b % 16)
        }
        i = i + 1
    }
    return out
}

// The fields worth keeping as a form-encoded body. Names starting with '_'
// are controls such as _gotcha and are dropped.
fn submission_body(fields: Map<String, String>) -> String {
    let mut pairs: List<String> = []
    for key in fields.keys() {
        if !text.starts_with(key, "_") {
            let value = fields.get(key) or ""
            pairs = pairs.push(encode(key) + "=" + encode(value))
        }
    }
    return "&".join(pairs)
}

fn padded(ms: Int) -> String {
    let mut out = "{ms}"
    while out.length() < 13 {
        out = "0" + out
    }
    return out
}

fn form_name(slug: String) -> String {
    return "form_" + slug
}

fn submission_prefix(slug: String) -> String {
    return "sub_" + slug + "_"
}

fn submission_name(slug: String, ms: Int, nonce: String) -> String {
    return submission_prefix(slug) + padded(ms) + "_" + nonce
}

fn failure_name(ms: Int, nonce: String) -> String {
    return "fail_" + padded(ms) + "_" + nonce
}

// A session file is named after the digest of its token, never the token.
fn session_name(token_digest: String) -> String {
    let bare = text.after(token_digest, ":") or token_digest
    return "session_" + bare
}

// The time in a sub_ or fail_ name: the 13 digits after the prefix.
fn time_of(name: String, prefix: String) -> Int {
    let rest = text.strip_prefix(name, prefix) or return -1
    let digits = text.before(rest, "_") or return -1
    return digits.to_int() or -1
}

// Form slugs in a listing, in name order.
fn form_slugs(names: List<String>) -> List<String> {
    let mut slugs: List<String> = []
    for name in names {
        let slug = text.strip_prefix(name, "form_") or {
            continue
        }
        slugs = slugs.push(slug)
    }
    return slugs
}

// Submission file names of one form, oldest first.
fn submissions_of(names: List<String>, slug: String) -> List<String> {
    let prefix = submission_prefix(slug)
    let mut found: List<String> = []
    for name in names {
        if text.starts_with(name, prefix) {
            found = found.push(name)
        }
    }
    return found
}

// fail_ names newer than `since`.
fn failures_since(names: List<String>, since: Int) -> Int {
    let mut count = 0
    for name in names {
        if text.starts_with(name, "fail_") && time_of(name, "fail_") > since {
            count = count + 1
        }
    }
    return count
}
