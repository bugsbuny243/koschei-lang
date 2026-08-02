fn main(caps: SystemCaps) {
    let net = caps.net.allow("https://api.example.com")
    let response = net.get("https://api.example.com/data") or return Error("request failed")
    println(response.text())
}
