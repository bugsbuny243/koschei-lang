# Koschei Library Threat Atlas v1

Purpose: study real-world library/framework failure modes and dual-use abuse surfaces, then derive Koschei language/runtime laws from them. This is not a claim that every listed project is insecure. Rows distinguish verified primary-source evidence from architectural surfaces that require deeper advisory review.

## Threat classes

- UDESER: untrusted deserialization / data becoming code
- RCE: remote/arbitrary code execution
- DOS: resource exhaustion / crash
- MEM: memory corruption / out-of-bounds / use-after-free
- INJECT: SQL/HTML/command/path/header injection or traversal
- AUTH: authority/permission/identity confusion
- SECRET: source/credential/key disclosure or side-channel
- SUPPLY: package/model/toolchain supply-chain compromise
- PARSE: parser/schema/normalization confusion
- BUILD: compiler/build/backend compromise or miscompile

## First 30 ecosystems

| # | Ecosystem | Primary attacker leverage / failure class | Evidence status | Koschei law to derive |
|---|---|---|---|---|
| 1 | React / React Server Components | RCE, UDESER, DOS, source exposure | VERIFIED: official React advisories (2025-2026) | Network input can never become executable authority; decode has hard CPU/memory budgets; source is non-observable by default |
| 2 | Node.js | DOS, AUTH, TLS/identity confusion, permission-model bypass, unbounded protocol state | VERIFIED: official Node.js 2026 security releases | Protocol state is bounded; identity is canonical before authorization; permission checks bind final target, not pre-normalized input |
| 3 | Express | XSS, dependency parser/router vulnerabilities; inherits Node security surface | VERIFIED: official Express security updates | Response construction is typed; redirect/content sinks reject raw attacker-controlled authority-bearing strings |
| 4 | Starlette / FastAPI substrate | multipart DOS, path traversal, Host/path poisoning | VERIFIED: official Starlette advisories | Request parsing gets explicit quotas; canonical path/authority is single-source; file projection is exact-object authority |
| 5 | Django | SQL injection, archive path traversal | VERIFIED: official Django 2025 security release notes | Query intent cannot be assembled from privileged raw strings; archive extraction is capability-scoped to exact destination objects |
| 6 | TensorFlow | untrusted model == program; OOB/heap failures in ops; parser/media attack surface | VERIFIED: TensorFlow security model + advisories | Model/data artifact never implies code authority; accelerator/native ops execute in bounded capability sandbox |
| 7 | PyTorch | pickle/unpickling RCE; weights-only still leaves DOS and possible memory-corruption surface | VERIFIED: PyTorch serialization docs | Serialized model is pure data by default; executable reconstruction requires separate explicit authority and bounded loader |
| 8 | Hugging Face Transformers | trust_remote_code permits arbitrary remote code/binaries; unsafe pickle heritage; mutable upstream revision risk | VERIFIED: official Transformers docs/model rules | Remote artifact identity is commit-bound; data and code are separate realities; remote code cannot obtain ambient process/network/secrets |
| 9 | pandas | pickle execution, eval/query execution, SQL/Excel/HTML injection surfaces when fed untrusted input | VERIFIED: pandas SECURITY.md explicitly documents these non-boundaries | Dataframe expressions and external sinks carry typed intent; untrusted data never crosses into evaluator authority implicitly |
| 10 | OpenSSL | memory-safety bugs, parser bugs, side-channel/key risks, certificate/identity mistakes | VERIFIED: official OpenSSL vulnerability index | Crypto is isolated behind constant-time/secret-non-observable contracts; parser and identity normalization are canonical and bounded |
| 11 | LLVM | supply-chain/tooling issues, memory-safety defects, binary-injection concerns, constant-time non-guarantees | VERIFIED: LLVM Security Transparency Reports | Backend is authenticated and reproducible; generated binary is evidence-bound to IR/policy/toolchain; secrets cannot rely on optimizer accidents |
| 12 | NumPy | native-extension/memory surface; object serialization and shape/resource abuse require focused review | ARCHITECTURAL; primary advisory deep-dive pending | Numeric domains are explicit and bounded; object-bearing arrays cannot silently become executable authority |
| 13 | SciPy | native numeric/parser/resource surface; algorithmic complexity and memory pressure require review | ARCHITECTURAL; pending | Expensive numerical operations must declare resource budgets and numeric domains |
| 14 | SymPy | symbolic-expression complexity / expression explosion / parser-eval boundaries | ARCHITECTURAL; pending | Symbolic expansion is budgeted; expression parsing cannot invoke ambient code or filesystem/network authority |
| 15 | JAX | JIT/XLA backend trust, accelerator resource exhaustion, shape/compile amplification | ARCHITECTURAL; pending | Compile intent is separated from device authority; graph size, shape and compile cost are statically/broker bounded |
| 16 | scikit-learn | model serialization/trust boundary; resource-exhaustive inputs/pipelines | ARCHITECTURAL; pending | Fitted model artifact is data; custom estimator code requires explicit authority; inference budgets are declared |
| 17 | Apache Spark | deserialization, distributed task authority, driver/executor lateral movement, resource amplification | ARCHITECTURAL; pending | Distributed task carries exact authority manifest; executor cannot inherit driver secrets/network/process rights |
| 18 | CUDA | native kernel memory safety, GPU resource exhaustion, device/host trust boundary | ARCHITECTURAL; pending | Device code receives bounded memory/resource capability; host secrets are not ambiently device-visible |
| 19 | Wasmtime / WebAssembly runtimes | sandbox escape risk, host-import authority, resource exhaustion | ARCHITECTURAL; pending | Imports are exact capabilities; fuel/memory/table budgets are mandatory; guest cannot manufacture host authority |
| 20 | Protocol Buffers | parser/resource exhaustion, schema confusion, oversized/recursive input | ARCHITECTURAL; pending | Schema decode is canonical, depth/size bounded, and cannot trigger code loading |
| 21 | gRPC | HTTP/2/resource amplification, metadata/header parsing, auth-context confusion | ARCHITECTURAL; pending | RPC identity and metadata are canonical before policy; stream/message quotas are first-class language contracts |
| 22 | SQLAlchemy | raw SQL/text escape hatches and unsafe dynamic query construction | ARCHITECTURAL; pending | Query is an Intent Reality with typed parameters; privileged raw-text execution requires a separate narrow capability |
| 23 | OpenTelemetry | telemetry data may leak secrets; exporter/network authority; cardinality/resource blowup | ARCHITECTURAL; pending | Observability is non-authoritative and redacted by type; telemetry has bounded cardinality and no secret read authority |
| 24 | libsodium | crypto misuse is reduced but key lifecycle/nonce/protocol misuse remains application risk | ARCHITECTURAL; pending | Secret objects are non-observable, affine/epoch-bound, and operations select safe constructions rather than raw primitives |
| 25 | web3.js | malicious/untrusted RPC provider, signing confusion, ABI/data trust, transaction intent mismatch | ARCHITECTURAL; pending | Provider identity is authenticated; transaction intent is independently reconstructed and exact-digest bound before signing |
| 26 | ethers.js | provider/signing/ABI trust surfaces similar to web3.js; wallet authority can be over-broad | ARCHITECTURAL; pending | Wallet/signing authority is one-shot, intent-bound, chain-bound and value/target constrained |
| 27 | Anchor (Solana) | account-validation mistakes, signer/account authority confusion, CPI trust boundaries | ARCHITECTURAL; pending | Account identity/ownership/signer relations are compiler-enforced Reality constraints, not optional runtime checks |
| 28 | Z3 | adversarial solver complexity / nontermination-like resource exhaustion; model/constraint trust | ARCHITECTURAL; pending | Proof/solver calls declare time/memory/complexity budget and produce evidence, never execution authority |
| 29 | Qiskit / Cirq / PennyLane | quantum backend trust, circuit/resource blowup, remote-provider result trust | ARCHITECTURAL; pending | Quantum contract is immutable; backend identity/resource budget/result evidence are authority-bound |
| 30 | npm / pip package ecosystems | typosquatting, dependency takeover, malicious install/build hooks, transitive authority inheritance | ARCHITECTURAL; ecosystem-wide primary-source deep-dive pending | Dependency has zero ambient authority; install/build hooks are non-default; package identity/revision/hash and requested capabilities are explicit |

## Immediate Koschei security laws extracted from verified rows

1. DATA != CODE AUTHORITY. A model, archive, serialized object, HTTP body or package cannot acquire executable authority merely by being parsed or loaded.
2. INTENT != AUTHORITY != EFFECT. A requested action, permission to perform it, and the external effect remain separate committed realities.
3. CANONICALIZE BEFORE POLICY. Path, host, certificate identity, package revision, chain id and object identity are canonical before an authorization decision is made.
4. EVERY PARSER HAS A BUDGET. Bytes, nesting, fields, files, CPU, memory, recursion and temporal frames are bounded before processing.
5. DEPENDENCIES RECEIVE ZERO AMBIENT POWER. No implicit network, process, filesystem, secrets, signing or device authority.
6. SOURCE/MODEL/SECRET NON-OBSERVABILITY IS A TYPE/RUNTIME PROPERTY, NOT A LOGGING CONVENTION.
7. BACKEND OUTPUT IS EVIDENCE-BOUND. Compiler, JIT, GPU, quantum and distributed backends must bind output to exact input IR, policy, backend identity and epoch.
8. EXTERNAL EFFECTS REQUIRE EXACT TARGET AUTHORITY. No prefix/path/string approximation and no authority widening through normalization differences.
9. RESOURCE EXHAUSTION IS A SECURITY FAILURE, NOT ONLY A PERFORMANCE BUG.
10. OBSERVATION NEVER IMPLIES CONTROL. Telemetry, model inspection and Sentinel evidence cannot mint execution authority.

## Primary sources used in v1

- React security advisories: https://github.com/react/react/security/advisories
- OpenSSL vulnerability index: https://openssl-library.org/news/vulnerabilities/
- LLVM Security Transparency Reports: https://www.llvm.org/docs/SecurityTransparencyReports.html
- TensorFlow security model: https://github.com/tensorflow/tensorflow/security
- PyTorch serialization security: https://docs.pytorch.org/docs/main/notes/serialization.html
- Hugging Face Transformers loading/security guidance: https://huggingface.co/docs/transformers/en/models
- pandas security policy: https://github.com/pandas-dev/pandas/security
- Django 5.2.7 security release notes: https://github.com/django/django/blob/main/docs/releases/5.2.7.txt
- Express security updates: https://expressjs.com/en/advanced/security-updates/
- Starlette security advisories: https://github.com/Kludex/starlette/security/advisories
- Node.js security releases: https://nodejs.org/en/blog/vulnerability/

## Next research pass

For rows marked ARCHITECTURAL, replace generic threat descriptions with concrete primary-source advisories/CVEs, exploit preconditions, patched versions, and a reproducible defensive test corpus. Do not add exploit weaponization; preserve only the minimum behavior needed to test Koschei prevention and blast-radius claims.
