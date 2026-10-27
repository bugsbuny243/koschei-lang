// secretscan: find leaked credentials in a directory before they ship.
//
//   ks run main.ks DIR
//   ks caps main.ks       # disk: read-only; network: none
//
// The scan reads DIR read-only and has no network authority, so whatever it
// finds cannot leave the machine; `ks caps` proves both. Each finding prints
// FILE:LINE, the kind of credential and only its public prefix and length,
// never the secret itself. The program fails (exit status 1) when anything
// is found, so a CI step can gate on it. Symbolic links are not followed;
// files that are not UTF-8 text and the .git directory are skipped.
//
// Recognised: private key blocks, AWS access key IDs, GitHub tokens, Slack
// tokens, Stripe live secret keys and Google API keys.

import text

// Characters that never occur inside these credentials and separate them
// from the surrounding code.
fn separators() -> String {
    return "\"'`=:,;()[]\{\}<>\t\r"
}

// The ASCII code of each byte, or -1 past the end.
fn code(data: Bytes, index: Int) -> Int {
    let value = data.get(index) or return -1
    return value
}

fn is_digit(value: Int) -> Bool {
    return value >= 48 && value <= 57
}

fn is_upper(value: Int) -> Bool {
    return value >= 65 && value <= 90
}

fn is_alnum(value: Int) -> Bool {
    return is_digit(value) || is_upper(value) || (value >= 97 && value <= 122)
}

// True when every byte of word from start on is in the class:
// "upper" (A-Z 0-9), "alnum" (A-Z a-z 0-9), "word" (alnum and _),
// "dash" (alnum and -), "key" (alnum, _ and -), "header" (A-Z and space).
fn all_in(word: String, start: Int, class: String) -> Bool {
    let data = word.to_bytes()
    let mut index = start
    while index < data.length() {
        let value = code(data, index)
        let mut ok = is_alnum(value)
        if class == "upper" {
            ok = is_upper(value) || is_digit(value)
        } else if class == "header" {
            ok = is_upper(value) || value == 32
        } else if class == "word" {
            ok = ok || value == 95
        } else if class == "dash" {
            ok = ok || value == 45
        } else if class == "key" {
            ok = ok || value == 95 || value == 45
        }
        if !ok {
            return false
        }
        index = index + 1
    }
    return true
}

// [kind, public prefix] when word is a credential of a known format, else [].
fn classify(word: String) -> List<String> {
    let none: List<String> = []
    let size = word.length()
    for prefix in ["AKIA", "ASIA"] {
        if text.starts_with(word, prefix) && size == 20 && all_in(word, 4, "upper") {
            return ["aws-access-key-id", prefix]
        }
    }
    for prefix in ["ghp_", "gho_", "ghu_", "ghs_", "ghr_"] {
        if text.starts_with(word, prefix) && size == 40 && all_in(word, 4, "alnum") {
            return ["github-token", prefix]
        }
    }
    if text.starts_with(word, "github_pat_") && size >= 50 && all_in(word, 11, "word") {
        return ["github-token", "github_pat_"]
    }
    for prefix in ["xoxb-", "xoxp-", "xoxa-", "xoxr-", "xoxs-"] {
        if text.starts_with(word, prefix) && size >= 15 && all_in(word, 5, "dash") {
            return ["slack-token", prefix]
        }
    }
    for prefix in ["sk_live_", "rk_live_"] {
        if text.starts_with(word, prefix) && size >= 24 && all_in(word, 8, "alnum") {
            return ["stripe-live-key", prefix]
        }
    }
    if text.starts_with(word, "AIza") && size == 39 && all_in(word, 4, "key") {
        return ["google-api-key", "AIza"]
    }
    return none
}

// A private key block header: "-----BEGIN ", an optional upper-case type
// ("RSA ", "EC " ...), then "PRIVATE KEY-----", as PEM files and keys
// embedded in JSON write it. "" for anything else.
fn private_key_header(line: String) -> String {
    let rest = text.after(line, "-----BEGIN ") or return ""
    let kind = text.before(rest, "PRIVATE KEY-----") or return ""
    if !all_in(kind, 0, "header") {
        return ""
    }
    return "-----BEGIN {kind}PRIVATE KEY-----"
}

// A cheap first test: only lines with a marker are split into words.
fn suspicious(line: String) -> Bool {
    for marker in ["PRIVATE KEY-----", "AKIA", "ASIA", "gh", "github_pat_", "xox", "_live_", "AIza"] {
        if line.contains(marker) {
            return true
        }
    }
    return false
}

fn words(line: String) -> List<String> {
    let none: List<String> = []
    let mut spaced = line
    let marks = separators().to_bytes()
    let mut index = 0
    while index < marks.length() {
        let mark = marks.slice(index, index + 1) or return none
        let separator = mark.to_text() or return none
        spaced = text.replace(spaced, separator, " ") or return none
        index = index + 1
    }
    let parts = spaced.split(" ") or return none
    return parts
}

// One line per finding: "FILE:LINE: KIND PREFIX... (N characters)".
fn scan(path: String, body: String) -> List<String> {
    let mut findings: List<String> = []
    let lines = body.split("\n") or return findings
    let mut number = 0
    for line in lines {
        number = number + 1
        if !suspicious(line) {
            continue
        }
        let header = private_key_header(line)
        if header != "" {
            findings = findings.push("{path}:{number}: private-key {header}")
            continue
        }
        for word in words(line) {
            let found = classify(word)
            let kind = found.get(0) or ""
            let prefix = found.get(1) or ""
            if kind != "" {
                findings = findings.push("{path}:{number}: {kind} {prefix}... ({word.length()} characters)")
            }
        }
    }
    return findings
}

fn main(caps: SystemCaps) -> Void or Error {
    let input = caps.input.allow(1)
    let none: List<String> = []
    let args = input.args() or none
    let root = args.get(0) or return Error("usage: secretscan DIR")
    let disk = caps.disk.allow_read_only(root)
    // A wrong path must not pass a CI gate as "nothing found".
    let top = disk.list(root) or return Error("secretscan: {root} is not a readable directory")
    let mut pending = [root]
    let mut next = 0
    let mut files = 0
    let mut skipped = 0
    let mut found = 0
    while next < pending.length() {
        let directory = pending.get(next) or ""
        next = next + 1
        let entries = disk.list(directory) or {
            skipped = skipped + 1
            continue
        }
        for name in entries {
            let path = "{directory}/{name}"
            let children = disk.list(path) or {
                let body = disk.read(path) or {
                    skipped = skipped + 1
                    continue
                }
                files = files + 1
                for finding in scan(path, body) {
                    println(finding)
                    found = found + 1
                }
                continue
            }
            if name != ".git" {
                pending = pending.push(path)
            }
        }
    }
    println("{files} files scanned, {skipped} skipped, {found} findings")
    if found > 0 {
        return Error("secretscan: {found} credential(s) found")
    }
    return
}
