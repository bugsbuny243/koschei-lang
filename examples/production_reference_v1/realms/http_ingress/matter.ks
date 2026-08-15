import json_gateway
import order_worker

fn handle_payload(body: String) -> String or Error {
    let canonical = json_gateway.canonicalize(body) or return
    let report = order_worker.process(10200, 25, 10100, 40, 500000, 100)
    return canonical + "\n" + report
}

fn main(caps: SystemCaps) {
    let server = caps.serve.allow(
        "127.0.0.1:18080",
        8,
        65536,
        65536,
        2000,
    )
    let body = server.exchange("accepted") or return
    let result = handle_payload(body) or return
    println(result)
}
