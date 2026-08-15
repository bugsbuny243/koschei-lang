fn fetch_snapshot(net: NetCaps, url: String) -> String or Error {
    let response = net.get(url) or return Error("market feed request failed")
    return response.text()
}

fn main() {}
