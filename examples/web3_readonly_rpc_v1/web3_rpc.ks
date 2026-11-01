// Project-local adapter: web3_rpc (requires explicit NetCaps)
// Read-only, single-origin EVM JSON-RPC client (experimental).
// A NetCaps token is passed explicitly; this module cannot widen origins.
// It sends two fixed POST requests: chain identity then latest block height.
// Strictly canonical JSON byte envelopes are required: noncanonical key
// order and whitespace are deliberately rejected until the imported-module
// native JSON codec supports identical validated decoding in both backends.
// Result envelope, id, jsonrpc and quantity are checked before return.
// NO transactions, signatures, user addresses, block-hash/finality proofs.
import platform_web3
import text

fn block_number(net: NetCaps, endpoint: String, chain_id: String) -> String or Error {
    let admitted = platform_web3.admit_read("eth_blockNumber", chain_id, "") or return Error("web3_rpc: chain or method denied")
    if admitted != "block-number" {
        return Error("web3_rpc: method denied")
    }
    let chain = net.post(endpoint, "application/json", "\{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"eth_chainId\",\"params\":[]\}") or return Error("web3_rpc: chain request failed")
    if chain.status() != 200 {
        return Error("web3_rpc: chain HTTP status denied")
    }
    let canonical_chain = chain.text()
    if canonical_chain != "\{\"id\":1,\"jsonrpc\":\"2.0\",\"result\":\"{chain_id}\"\}" {
        return Error("web3_rpc: mismatching RPC chain identity/envelope")
    }

    let block = net.post(endpoint, "application/json", "\{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"eth_blockNumber\",\"params\":[]\}") or return Error("web3_rpc: block request failed")
    if block.status() != 200 {
        return Error("web3_rpc: block HTTP status denied")
    }
    let canonical_block = block.text()
    let after_prefix = text.strip_prefix(canonical_block, "\{\"id\":2,\"jsonrpc\":\"2.0\",\"result\":\"") or return Error("web3_rpc: invalid block envelope/id")
    let result = text.strip_suffix(after_prefix, "\"\}") or return Error("web3_rpc: block response has extra fields")
    if !platform_web3.quantity(result) {
        return Error("web3_rpc: noncanonical or invalid block quantity")
    }
    return result
}
