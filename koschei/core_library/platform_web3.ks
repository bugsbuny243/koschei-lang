// Pure, read-only EVM JSON-RPC admission. No signing or RPC transport.
fn hex_digit(c: Int) -> Bool {
    return (c >= 48 && c <= 57) || (c >= 97 && c <= 102)
}
fn quantity(value: String) -> Bool {
    let bytes = value.to_bytes()
    if bytes.length() < 3 || bytes.length() > 66 ||
       (bytes.get(0) or -1) != 48 ||
       (bytes.get(1) or -1) != 120 {
        return false
    }
    if bytes.length() > 3 && (bytes.get(2) or -1) == 48 { return false }
    let mut i = 2
    while i < bytes.length() {
        if !hex_digit(bytes.get(i) or -1) { return false }
        i = i + 1
    }
    return true
}
fn address(value: String) -> Bool {
    let bytes = value.to_bytes()
    if bytes.length() != 42 || (bytes.get(0) or -1) != 48 ||
       (bytes.get(1) or -1) != 120 {
        return false
    }
    let mut i = 2
    while i < bytes.length() {
        if !hex_digit(bytes.get(i) or -1) { return false }
        i = i + 1
    }
    return true
}
fn admit_read(method: String, chain_id: String, account: String) -> Result<String, Error> {
    if !quantity(chain_id) || chain_id == "0x0" {
        return Err(Error("platform_web3: invalid chain identifier"))
    }
    if method == "eth_chainId" && account == "" { return Ok("chain-id") }
    if method == "eth_blockNumber" && account == "" { return Ok("block-number") }
    if method == "eth_getBalance" && address(account) { return Ok("balance") }
    return Err(Error("platform_web3: RPC method or account forbidden"))
}
