// Koschei Forms: input rules. Pure: no capability reaches this module.

import json
import text

// A form name: 1 to 40 lowercase letters, digits or '-'.
fn valid_slug(slug: String) -> Bool {
    let data = slug.to_bytes()
    if data.length() < 1 || data.length() > 40 {
        return false
    }
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        let letter = b >= 97 && b <= 122
        let digit = b >= 48 && b <= 57
        if !letter && !digit && b != 45 {
            return false
        }
        i = i + 1
    }
    return true
}

// Where a form sends its visitor after a submission: empty (the built-in
// thank-you page) or an http(s) URL of printable ASCII without spaces,
// quotes or angle brackets. Only the administrator sets it, never the
// submitter, so the form cannot be used as an open redirect.
fn valid_redirect(url: String) -> Bool {
    if url.length() == 0 {
        return true
    }
    if url.length() > 500 {
        return false
    }
    if !text.starts_with(url, "https://") && !text.starts_with(url, "http://") {
        return false
    }
    let data = url.to_bytes()
    let mut i = 0
    while i < data.length() {
        let b = data.get(i) or 0
        if b <= 32 || b >= 127 || b == 34 || b == 39 || b == 60 || b == 62 {
            return false
        }
        i = i + 1
    }
    return true
}

// A spam bot fills every field; people never see the hidden _gotcha field.
fn is_spam(fields: Map<String, String>) -> Bool {
    let trap = fields.get("_gotcha") or ""
    return trap.length() > 0
}

// The fields worth keeping, as a JSON object. Names starting with '_' are
// controls such as _gotcha and are dropped.
fn submission_json(fields: Map<String, String>) -> String {
    let mut members: Map<String, String> = {}
    for key in fields.keys() {
        if !text.starts_with(key, "_") {
            let value = fields.get(key) or ""
            members = members.set(key, json.string(value))
        }
    }
    return json.object(members)
}

// Constant-shape comparison of two hex digests of equal length.
fn same_digest(left: String, right: String) -> Bool {
    let a = left.to_bytes()
    let b = right.to_bytes()
    if a.length() != b.length() || a.length() == 0 {
        return false
    }
    let mut difference = 0
    let mut i = 0
    while i < a.length() {
        let x = a.get(i) or 0
        let y = b.get(i) or 0
        if x != y {
            difference = difference + 1
        }
        i = i + 1
    }
    return difference == 0
}
