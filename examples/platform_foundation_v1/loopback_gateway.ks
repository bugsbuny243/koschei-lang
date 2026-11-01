// Real bounded loopback HTTP gateway using the pure platform_web rules.
// PORT is replaced with a free loopback port by integration tests before
// compilation, because ServeCaps bind addresses are static literals.
import platform_web

fn handle(server: ServeCaps) -> Int {
    let mut rounds = 0
    let mut served = 0
    while rounds < 5 {
        rounds = rounds + 1
        let request = server.accept() or { continue }
        let route = platform_web.admit(request.method(), request.path()) or "DENY"
        let size = request.body_bytes().length()
        let mut status = 404
        let mut response = "denied"
        if route == "health" {
            status = 200
            response = "ok"
        } else if route == "status" {
            status = 200
            response = "ready"
        } else if route == "jobs-create" {
            if platform_web.body_within_budget(size, 1024) {
                status = 201
                response = "accepted"
            } else {
                status = 413
                response = "body-too-large"
            }
        }
        let sent = server.reply(status, response) or { continue }
        served = served + 1
    }
    return served
}

fn main(caps: SystemCaps) {
    // The ONLY effect authority: an explicit, bounded local listener.
    let server = caps.serve.allow("127.0.0.1:PORT", 5, 4096, 256, 3000)
    println("web-served={handle(server)}")
}
