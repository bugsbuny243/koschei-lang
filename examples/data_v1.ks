fn main() {
    let payload = parse_json("\{\"balance\":1.00,\"active\":true,\"roles\":[\"owner\"]\}") or return
    let canonical = encode_json(payload) or return
    println(canonical)
}
