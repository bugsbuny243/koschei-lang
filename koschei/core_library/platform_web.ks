// Koschei Core Library: platform_web
// Pure, bounded HTTP route admission; importing this grants no ServeCaps.
fn route_path(path: String) -> Bool {
    let bytes = path.to_bytes()
    if bytes.length() == 0 || bytes.length() > 256 ||
       (bytes.get(0) or -1) != 47 {
        return false
    }
    let mut i = 0
    let mut slash_before = false
    while i < bytes.length() {
        let c = bytes.get(i) or return false
        let valid = (c >= 65 && c <= 90) || (c >= 97 && c <= 122) ||
                    (c >= 48 && c <= 57) || c == 47 || c == 45 || c == 95
        if !valid || (c == 47 && slash_before) {
            return false
        }
        slash_before = c == 47
        i = i + 1
    }
    return bytes.length() == 1 || !slash_before
}
fn admit(method: String, path: String) -> Result<String, Error> {
    if !route_path(path) {
        return Err(Error("platform_web: malformed route"))
    }
    if method == "GET" && path == "/health" { return Ok("health") }
    if method == "GET" && path == "/v1/status" { return Ok("status") }
    if method == "POST" && path == "/v1/jobs" { return Ok("jobs-create") }
    return Err(Error("platform_web: route not authorized"))
}
fn body_within_budget(bytes: Int, limit: Int) -> Bool {
    return bytes >= 0 && limit > 0 && limit <= 1048576 && bytes <= limit
}
