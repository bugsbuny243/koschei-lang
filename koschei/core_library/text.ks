// Koschei Core Library: text
//
// Written in Koschei on top of the String kernel (length, contains, trim,
// split, join). A search pattern that must locate something (separator,
// needle, old text) may not be empty: an empty pattern has no single meaning,
// so it produces None or an Error value instead of a guessed answer.

import list

fn is_empty(value: String) -> Bool {
    return value.length() == 0
}

fn is_blank(value: String) -> Bool {
    return value.trim().length() == 0
}

// Prefix and suffix tests compare UTF-8 bytes: a valid UTF-8 text starts (or
// ends) with another exactly when its bytes do, and a byte slice never needs
// more than the value itself, so any String within the value budget works.
fn starts_with(value: String, prefix: String) -> Bool {
    let rest = strip_prefix(value, prefix) or return false
    return true
}

fn ends_with(value: String, suffix: String) -> Bool {
    let rest = strip_suffix(value, suffix) or return false
    return true
}

fn strip_prefix(value: String, prefix: String) -> Option<String> {
    let data = value.to_bytes()
    let wanted = prefix.to_bytes()
    if data.length() < wanted.length() {
        return None()
    }
    let head = data.slice(0, wanted.length()) or return None()
    if head != wanted {
        return None()
    }
    let tail = data.slice(wanted.length(), data.length()) or return None()
    let rest = tail.to_text() or return None()
    return Some(rest)
}

// Returns the text before a trailing `suffix`, or None when the value does not
// end with it.
fn strip_suffix(value: String, suffix: String) -> Option<String> {
    let data = value.to_bytes()
    let wanted = suffix.to_bytes()
    if data.length() < wanted.length() {
        return None()
    }
    let cut = data.length() - wanted.length()
    let tail = data.slice(cut, data.length()) or return None()
    if tail != wanted {
        return None()
    }
    let head = data.slice(0, cut) or return None()
    let rest = head.to_text() or return None()
    return Some(rest)
}

// Text before the first occurrence of `separator`. None also when the value
// holds more pieces than one List may (KS3502): the answer is not computed.
fn before(value: String, separator: String) -> Option<String> {
    if separator.length() == 0 {
        return None()
    }
    let pieces = value.split(separator) or return None()
    if pieces.length() < 2 {
        return None()
    }
    return pieces.get(0)
}

// Text after the first occurrence of `separator`; None as for `before`.
fn after(value: String, separator: String) -> Option<String> {
    if separator.length() == 0 {
        return None()
    }
    let pieces = value.split(separator) or return None()
    if pieces.length() < 2 {
        return None()
    }
    let rest = separator.join(list.drop(pieces, 1)) or return None()
    return Some(rest)
}

// Number of non-overlapping occurrences, counted left to right.
fn count(value: String, needle: String) -> Result<Int, Error> {
    if needle.length() == 0 {
        return Err(Error("text.count: needle must not be empty"))
    }
    let pieces = value.split(needle) or return Err(Error("text.count: more occurrences than one List may hold (KS3502)"))
    return Ok(pieces.length() - 1)
}

// Replaces every non-overlapping occurrence, left to right.
fn replace(value: String, old: String, replacement: String) -> Result<String, Error> {
    if old.length() == 0 {
        return Err(Error("text.replace: old text must not be empty"))
    }
    let pieces = value.split(old) or return Err(Error("text.replace: more occurrences than one List may hold (KS3502)"))
    let replaced = replacement.join(pieces) or return Err(Error("text.replace: join failed"))
    return Ok(replaced)
}

// Lines separated by "\n". One trailing "\r" is removed from each line, and a
// final "\n" does not start an extra empty line.
fn lines(value: String) -> List<String> {
    let mut out: List<String> = []
    if value.length() == 0 {
        return out
    }
    let pieces = value.split("\n")
    let mut index = 0
    for piece in pieces {
        let is_final_empty = index == pieces.length() - 1 && piece.length() == 0
        if !is_final_empty {
            let line = strip_suffix(piece, "\r") or piece
            out = out.push(line)
        }
        index = index + 1
    }
    return out
}

// Non-empty pieces separated by spaces, tabs, carriage returns or newlines.
fn words(value: String) -> List<String> {
    let mut pieces = [value]
    for separator in [" ", "\t", "\r", "\n"] {
        let mut next: List<String> = []
        for piece in pieces {
            for part in piece.split(separator) {
                if part.length() > 0 {
                    next = next.push(part)
                }
            }
        }
        pieces = next
    }
    return pieces
}

// The distinct values in ascending character order: a canonical set of names.
// Insertion keeps the work quadratic, which suits the small name sets the
// library's guardians use.
fn unique_sorted(values: List<String>) -> List<String> {
    let mut out: List<String> = []
    for value in values {
        if out.contains(value) {
            continue
        }
        let mut next: List<String> = []
        let mut placed = false
        for current in out {
            if !placed && value < current {
                next = next.push(value)
                placed = true
            }
            next = next.push(current)
        }
        if !placed {
            next = next.push(value)
        }
        out = next
    }
    return out
}
