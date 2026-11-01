// Koschei Core Library: web3_rpc
// Read-only, single-origin EVM JSON-RPC client (experimental).
// A NetCaps token is passed explicitly; this module cannot widen origins.
// It sends two fixed POST requests: chain identity then latest block height.
// JSON is parsed through the shared strict parser and canonical encoder;
// result envelope, id, jsonrpc and quantity are all checked before return.
// NO transactions, signatures, user addresses, block-hash/finality proofs.
import platform_web3
import text

fn block_number(net: NetCaps, endpoint: String, chain_id: String) -> String or Error {
    let admitted = platform_web3.admit_read("eth_blockNumber", chain_id, "") or return Error("web3_rpc: chain or method denied")
    if admitted != "block-number" {
        return Error("web3_rpc: method denied")
    }
    let chain = net.post(endpoint, "application/json", "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"eth_chainId\",\"params\":[]}") or return Error("web3_rpc: chain request failed")
    if chain.status() != 200 {
        return Error("web3_rpc: chain HTTP status denied")
    }
    let chain_value = parse_json(chain.text()) or return Error("web3_rpc: malformed chain JSON")
    let canonical_chain = encode_json(chain_value) or return Error("web3_rpc: chain JSON cannot be encoded")
    if canonical_chain != "{\"id\":1,\"jsonrpc\":\"2.0\",\"result\":\"{chain_id}\"}" {
        return Error("web3_rpc: mismatching RPC chain identity/envelope")
    }

    let block = net.post(endpoint, "application/json", "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"eth_blockNumber\",\"params\":[]}") or return Error("web3_rpc: block request failed")
    if block.status() != 200 {
        return Error("web3_rpc: block HTTP status denied")
    }
    let block_value = parse_json(block.text()) or return Error("web3_rpc: malformed block JSON")
    let canonical_block = encode_json(block_value) or return Error("web3_rpc: block JSON cannot be encoded")
    let after_prefix = text.strip_prefix(canonical_block, "{\"id\":2,\"jsonrpc\":\"2.0\",\"result\":\"") or return Error("web3_rpc: invalid block envelope/id")
    let result = text.strip_suffix(after_prefix, "\"}") or return Error("web3_rpc: block response has extra fields")
    if !platform_web3.quantity(result) {
        return Error("web3_rpc: noncanonical or invalid block quantity")
    }
    return result
}
