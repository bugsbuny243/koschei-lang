// One runnable, no-capability composition of four independent libraries.
import platform_web
import platform_web3
import platform_ai
import platform_kernel

fn main() {
    let web = platform_web.admit("GET", "/health") or "DENY"
    let web_denied = platform_web.admit("POST", "/health") or "DENY"
    println("web={web} denied={web_denied}")

    let chain = platform_web3.admit_read("eth_blockNumber", "0x1", "") or "DENY"
    let signing = platform_web3.admit_read("eth_sendTransaction", "0x1", "") or "DENY"
    println("web3={chain} signed={signing}")

    let ai = platform_ai.admit("local-model", ["local-model"], 2048, 4096, 128) or "DENY"
    let ai_denied = platform_ai.admit("unknown", ["local-model"], 2048, 4096, 128) or "DENY"
    println("ai={ai} denied={ai_denied}")

    let owned = platform_kernel.claimed_frame(1048576, 16, [1048576, 1052672], 1052672)
    let duplicate = platform_kernel.claimed_frame(1048576, 16, [1048576, 1048576], 1048576)
    println("kernel-claimed={owned} forged={duplicate}")
}
