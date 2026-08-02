fn main() {
    let value = parse_json("\{\"b\":2,\"a\":1.00\}") or return
    let canonical = encode_json(value) or return
    println(canonical)
}
