// integrity: record the digests of a directory's files, then prove that
// nothing changed.
//
//   ks run main.ks snapshot DIR > manifest.txt
//   ks run main.ks verify DIR < manifest.txt
//   ks caps main.ks       # disk: read-only; network: none
//
// Every file is named by its SHA3-256 digest (`secure.hash_bytes`), so a
// change to any byte shows. The audited digest takes at most 1 MiB, so a
// larger file is digested in 1 MiB chunks and recorded as
// "sha3-256-chunks:" and the domain-separated digest of those chunk digests
// (`secure.digest`); the distinct tag keeps a small file that holds the
// serialized chunk digests from matching the large file. The tool reads DIR read-only and has neither
// write nor network authority: the manifest goes to standard output and
// comes back on standard input. A manifest line is "DIGEST PATH", with PATH
// relative to DIR. A symbolic link (never followed) and an entry that is
// not a regular file (a FIFO, socket or device, never opened as a stream)
// are recorded as "skipped", so a change of kind shows; .git is left out.
// Any other entry that cannot be digested (over the 16 MiB value budget,
// unreadable), a name that holds a newline (a manifest line cannot) and a
// manifest over the 16 MiB that `verify` reads fail the snapshot rather than
// leaving a file unchecked.
//
// `verify` prints CHANGED, MISSING and NEW lines and fails (exit status 1)
// when there is any difference, so a CI step or a server can gate on it.

import secure
import text

fn file_digest(data: Bytes) -> String or Error {
    let chunk_size = 1048576
    if data.length() <= chunk_size {
        let whole = secure.hash_bytes(data) or return Error("integrity: a file could not be digested")
        return whole
    }
    let mut parts: List<String> = []
    let mut start = 0
    while start < data.length() {
        let mut end = start + chunk_size
        if end > data.length() {
            end = data.length()
        }
        let chunk = data.slice(start, end) or return
        let digest = secure.hash_bytes(chunk) or return Error("integrity: a file could not be digested")
        parts = parts.push(digest)
        start = end
    }
    let combined = secure.digest("koschei.example.integrity.chunks/v1", parts) or return Error("integrity: a file could not be digested")
    let hex = text.after(combined, "sha3-256:") or return Error("integrity: a file could not be digested")
    return "sha3-256-chunks:{hex}"
}

// A read failure that loses no file content: a symbolic link (never
// followed) or an entry that is not a regular file (a FIFO, socket or
// device, never opened as a stream). Matched on the message's fixed start,
// never on the path it ends with.
fn skipped_by_design(reason: String) -> Bool {
    return text.starts_with(reason, "KS3402: Disk kapsamı sembolik bağ üzerinden aşılamaz; KS3405: ") || text.starts_with(reason, "Dosya okunamadı: düzenli dosya değil: ")
}

// The Error text of a failed read, or "" when it succeeded.
fn failure(result: Bytes or Error) -> String {
    let data = result or {
        return "{result}"
    }
    return ""
}

// Every entry under root, by path relative to root, walking each directory
// in name order. Error when root itself cannot be listed.
fn digests(disk: DiskReadCaps, root: String) -> Map<String, String> or Error {
    let mut found: Map<String, String> = {}
    let top = disk.list(root) or return Error("integrity: {root} is not a readable directory")
    let mut pending = [""]
    let mut next = 0
    while next < pending.length() {
        let relative = pending.get(next) or ""
        next = next + 1
        let mut directory = root
        let mut prefix = ""
        if relative != "" {
            directory = "{root}/{relative}"
            prefix = "{relative}/"
        }
        let entries = disk.list(directory) or return Error("integrity: {relative} cannot be listed")
        for name in entries {
            let path = "{prefix}{name}"
            if path.contains("\n") {
                return Error("integrity: a name holds a newline, which a manifest line cannot: {path}")
            }
            let children = disk.list("{root}/{path}") or {
                let data = disk.read_bytes("{root}/{path}") or {
                    let reason = failure(disk.read_bytes("{root}/{path}"))
                    if !skipped_by_design(reason) {
                        return Error("integrity: {path} cannot be digested: {reason}")
                    }
                    found = found.set(path, "skipped")
                    continue
                }
                let digest = file_digest(data) or return
                found = found.set(path, digest)
                continue
            }
            if name != ".git" {
                pending = pending.push(path)
            }
        }
    }
    return found
}

fn verify(current: Map<String, String>, manifest: String) -> Int or Error {
    let mut recorded: Map<String, String> = {}
    let lines = manifest.split("\n") or return Error("integrity: the manifest has too many lines")
    for line in lines {
        if line == "" {
            continue
        }
        let digest = text.before(line, " ") or return Error("integrity: malformed manifest line: {line}")
        let path = text.after(line, " ") or return Error("integrity: malformed manifest line: {line}")
        recorded = recorded.set(path, digest)
    }
    let mut differences = 0
    for path in current.keys() {
        let now = current.get(path) or ""
        if !recorded.contains(path) {
            println("NEW {path}")
            differences = differences + 1
        } else {
            let before = recorded.get(path) or ""
            if before != now {
                println("CHANGED {path}")
                differences = differences + 1
            }
        }
    }
    for path in recorded.keys() {
        if !current.contains(path) {
            println("MISSING {path}")
            differences = differences + 1
        }
    }
    println("{current.keys().length()} entries checked, {differences} differences")
    return differences
}

fn main(caps: SystemCaps) -> Void or Error {
    let input = caps.input.allow(16777216)
    let none: List<String> = []
    let args = input.args() or none
    let mode = args.get(0) or ""
    let root = args.get(1) or ""
    if (mode != "snapshot" && mode != "verify") || root == "" || args.length() != 2 {
        return Error("usage: integrity snapshot DIR > manifest.txt | integrity verify DIR < manifest.txt")
    }
    let current = digests(caps.disk.allow_read_only(root), root) or return
    if mode == "snapshot" {
        // verify reads the manifest with a 16 MiB input budget.
        let mut lines: List<String> = []
        let mut size = 0
        for path in current.keys() {
            let digest = current.get(path) or ""
            let line = "{digest} {path}"
            size = size + line.to_bytes().length() + 1
            if size > 16777216 {
                return Error("integrity: the manifest would exceed the 16 MiB that verify reads; snapshot a smaller directory")
            }
            lines = lines.push(line)
        }
        for line in lines {
            println(line)
        }
        return
    }
    let manifest = input.read_text() or return Error("integrity: the manifest must be UTF-8 text of at most 16 MiB")
    let differences = verify(current, manifest) or return
    if differences > 0 {
        return Error("integrity: {differences} difference(s)")
    }
    return
}
