// Koschei Core Library: list
//
// Written in Koschei. Every function is total and never mutates its input:
// a result list is always a fresh value. Index arguments outside the valid
// range produce an Error value; they are never clamped silently.

fn is_empty<T>(items: List<T>) -> Bool {
    return items.length() == 0
}

fn first<T>(items: List<T>) -> Option<T> {
    if items.length() == 0 {
        return None()
    }
    return items.get(0)
}

fn last<T>(items: List<T>) -> Option<T> {
    if items.length() == 0 {
        return None()
    }
    return items.get(items.length() - 1)
}

fn concat<T>(left: List<T>, right: List<T>) -> List<T> {
    let mut out = left
    for item in right {
        out = out.push(item)
    }
    return out
}

fn reverse<T>(items: List<T>) -> List<T> {
    let mut out: List<T> = []
    let mut index = items.length() - 1
    while index >= 0 {
        let item = items.get(index) or return out
        out = out.push(item)
        index = index - 1
    }
    return out
}

// Drops the first `count` items. A non-positive count keeps every item and a
// count beyond the length yields an empty list, mirroring List.take.
fn drop<T>(items: List<T>, count: Int) -> List<T> {
    let mut out: List<T> = []
    let mut index = 0
    for item in items {
        if index >= count {
            out = out.push(item)
        }
        index = index + 1
    }
    return out
}

// Items from `start` up to but excluding `end`; requires 0 <= start <= end <= length.
fn slice<T>(items: List<T>, start: Int, end: Int) -> Result<List<T>, Error> {
    if start < 0 || end < start || end > items.length() {
        return Err(Error("list.slice: range is outside the list"))
    }
    let mut out: List<T> = []
    let mut index = 0
    for item in items {
        if index >= start && index < end {
            out = out.push(item)
        }
        index = index + 1
    }
    return Ok(out)
}

// Inserts `item` before position `index`; requires 0 <= index <= length.
fn insert_at<T>(items: List<T>, index: Int, item: T) -> Result<List<T>, Error> {
    if index < 0 || index > items.length() {
        return Err(Error("list.insert_at: index is outside the list"))
    }
    let mut out: List<T> = []
    let mut position = 0
    for current in items {
        if position == index {
            out = out.push(item)
        }
        out = out.push(current)
        position = position + 1
    }
    if index == items.length() {
        out = out.push(item)
    }
    return Ok(out)
}

// Removes the item at `index`; requires 0 <= index < length.
fn remove_at<T>(items: List<T>, index: Int) -> Result<List<T>, Error> {
    if index < 0 || index >= items.length() {
        return Err(Error("list.remove_at: index is outside the list"))
    }
    let mut out: List<T> = []
    let mut position = 0
    for current in items {
        if position != index {
            out = out.push(current)
        }
        position = position + 1
    }
    return Ok(out)
}

// Replaces the item at `index`; requires 0 <= index < length.
fn replace_at<T>(items: List<T>, index: Int, item: T) -> Result<List<T>, Error> {
    if index < 0 || index >= items.length() {
        return Err(Error("list.replace_at: index is outside the list"))
    }
    let mut out: List<T> = []
    let mut position = 0
    for current in items {
        if position == index {
            out = out.push(item)
        } else {
            out = out.push(current)
        }
        position = position + 1
    }
    return Ok(out)
}
