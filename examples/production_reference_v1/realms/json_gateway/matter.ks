fn canonicalize(payload: String) -> String or Error {
    let value = parse_json(payload) or return Error("invalid json")
    return encode_json(value) or return Error("json encoding failed")
}

fn main() {}
