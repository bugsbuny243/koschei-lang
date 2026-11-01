# Read-only Web3 JSON-RPC experiment (Koschei Lang)

The `web3_rpc.ks` file is a **project-local module**, not a registered
Core Library member. This preserves the Core Library's zero-authority
import contract.

This executable `.ks` adapter uses exactly one explicit `NetCaps` origin
and two fixed `application/json` HTTP POST messages: `eth_chainId` and
`eth_blockNumber`. No user-provided method is interpolated onto the wire.
The first reply must contain the exact expected chain identifier (canonical
`0x1` in the fixture) and matching JSON-RPC version and ID; the second
must carry a canonical non-negative `0x` hex block number. Both replies
must be HTTP 200 with **byte-exact canonical JSON envelopes** (fixed key order and no formatting whitespace), bounded by the native/interpreter network response limit, and *no extra response fields*. Full JSON normalization from imported `.ks` modules is not yet supported equally by the interpreter and native compiler.
Duplicate keys, mismatched IDs, error envelopes, noncanonical quantities,
unexpected redirects, unexpected chain IDs, malformed JSON and oversized
responses are rejected. The existing network broker already enforces the
origin, request/response budgets and UTF-8.

The mock endpoint is bound to loopback and is never installed as a live
Web3 Hub integration. The test creates it dynamically and replaces the
static PORT in `main.ks`. Run the integration tests:

```sh
python -m pytest -q tests/test_platform_web3_rpc_v1.py
```

**Limitations:** This does not verify the node's honesty, TLS pinning,
Ethereum consensus, block hash, finality, reorganization handling, Merkle
proofs, transaction receipts, remote chain availability or production
service reliability. A changing block height is a reported *observation*
from an origin-restricted peer, never a security attestation. Wallet and
transaction signing/sending are absent by design. The native networking
backend is currently Linux/amd64 via the capability broker.
