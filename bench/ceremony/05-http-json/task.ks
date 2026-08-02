fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://api.example.com")
    let response = net.get("https://api.example.com/data") or return
    let value = parse_json(response.text()) or return
    println(encode_json(value) or return)
}
