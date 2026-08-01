fn main() {
    let payload = parse_json("\{\"balance\":1.00,\"active\":true,\"roles\":[\"owner\"]\}") or return Error("invalid JSON payload")
    let canonical = encode_json(payload) or return Error("Data encoding failed")
    println(canonical)
}
