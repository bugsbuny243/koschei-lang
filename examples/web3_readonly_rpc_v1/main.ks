// Live local HTTP mock is supplied by tests; never connect to a public RPC.
// PORT is replaced with an ephemeral loopback port before compilation.
import web3_rpc

fn main(caps: SystemCaps) {
    let net = caps.net.allow("http://127.0.0.1:PORT")
    let block = web3_rpc.block_number(net, "http://127.0.0.1:PORT/rpc", "0x1") or "DENY"
    println("web3-rpc-block={block}")
}
