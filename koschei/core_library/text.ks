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

fn starts_with(value: String, prefix: String) -> Bool {
    if prefix.length() == 0 {
        return true
    }
    if value.length() < prefix.length() {
        return false
    }
    // split finds the leftmost occurrence first, so the first piece is empty
    // exactly when the value begins with the prefix.
    let head = value.split(prefix).get(0) or return false
    return head.length() == 0
}

fn ends_with(value: String, suffix: String) -> Bool {
    let rest = strip_suffix(value, suffix) or return false
    return true
}

fn strip_prefix(value: String, prefix: String) -> Option<String> {
    if !starts_with(value, prefix) {
        return None()
    }
    if prefix.length() == 0 {
        return Some(value)
    }
    let rest = prefix.join(list.drop(value.split(prefix), 1)) or return None()
    return Some(rest)
}

// Returns the text before a trailing `suffix`, or None when the value does not
// end with it.
//
// split matches left to right without overlap, so when the suffix overlaps its
// own previous match ("aaa" ends with "aa") the last piece is not empty even
// though the value ends with the suffix. With pieces = value.split(suffix) and
// tail = the last piece (shorter than the suffix), the last len(suffix)
// characters of the value are suffix[len(tail):] + tail. They equal the suffix
// exactly when the suffix ends with tail (suffix = core + tail) and also ends
// with core; the second check also yields lead = suffix[:len(tail)]. Both
// recursive calls take the suffix as their value, which is strictly shorter
// than the current value, so the recursion always terminates.
fn strip_suffix(value: String, suffix: String) -> Option<String> {
    if suffix.length() == 0 {
        return Some(value)
    }
    if value.length() < suffix.length() {
        return None()
    }
    let pieces = value.split(suffix)
    let tail = list.last(pieces) or return None()
    let head = suffix.join(pieces.take(pieces.length() - 1)) or return None()
    if tail.length() == 0 {
        return Some(head)
    }
    if tail.length() >= suffix.length() {
        return None()
    }
    let core = strip_suffix(suffix, tail) or return None()
    let lead = strip_suffix(suffix, core) or return None()
    return Some(head + lead)
}

// Text before the first occurrence of `separator`.
fn before(value: String, separator: String) -> Option<String> {
    if separator.length() == 0 {
        return None()
    }
    let pieces = value.split(separator)
    if pieces.length() < 2 {
        return None()
    }
    return pieces.get(0)
}

// Text after the first occurrence of `separator`.
fn after(value: String, separator: String) -> Option<String> {
    if separator.length() == 0 {
        return None()
    }
    let pieces = value.split(separator)
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
    return Ok(value.split(needle).length() - 1)
}

// Replaces every non-overlapping occurrence, left to right.
fn replace(value: String, old: String, replacement: String) -> Result<String, Error> {
    if old.length() == 0 {
        return Err(Error("text.replace: old text must not be empty"))
    }
    let replaced = replacement.join(value.split(old)) or return Err(Error("text.replace: join failed"))
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
