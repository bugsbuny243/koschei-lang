# Financial Exchange Reference — P0/P1

This directory is Koschei's first financial-infrastructure reference workload.
It is intentionally small: a deterministic pair matcher plus the first exact
Decimal ABI workload, not a production exchange.

## P0 — matching security / determinism contract

- Prices are integer `price_ticks`; quantities are integer `quantity_lots`.
- `Float` is forbidden in the financial matching core.
- The matching module accepts no capability token and therefore has no disk,
  network, environment, or process authority.
- A buy crosses a sell only when `buy.price_ticks >= sell.price_ticks`.
- Fill quantity is the smaller remaining lot quantity.
- The older order (lower sequence) is maker; the maker limit is execution price.
- Invalid or non-crossing pairs return `None` rather than fabricating a fill.
- Interpreter and native Go output are required to match byte-for-byte.

Run it:

```bash
ks check examples/financial_exchange/main.ks
ks caps examples/financial_exchange/main.ks
ks run examples/financial_exchange/main.ks
ks build examples/financial_exchange/main.ks -o /tmp/koschei-matching
/tmp/koschei-matching
```

Expected output:

```text
TRADE maker=S-0001 taker=B-0001 price_ticks=10100 quantity_lots=25
NO_TRADE
NO_TRADE
```

## P1 — exact Decimal contract

`decimal_v1.ks` exercises the first exact fixed-scale financial ABI:

```koschei
let bid = decimal("101.2500", 4) or return
let fee = decimal("0.1250", 4) or return
let total = decimal_add(bid, fee) or return
println(decimal_text(total))
```

The Decimal runtime never parses through binary Float. Values carry signed-int64
atoms plus an explicit scale. Different scales, int64 overflow and lossy input
fail closed. Direct Decimal operators are intentionally disabled in P1; use the
fallible `decimal_add`, `decimal_sub` and `decimal_cmp` contracts.

```bash
ks check examples/financial_exchange/decimal_v1.ks
ks run examples/financial_exchange/decimal_v1.ks
ks build examples/financial_exchange/decimal_v1.ks -o /tmp/koschei-decimal
/tmp/koschei-decimal
```

## What this reference does not claim

P0/P1 are not a full order book, venue, custody system, settlement system, or
regulated exchange. They turn financial correctness requirements into executable
compiler/runtime tests. Later phases add book-level price-time priority,
recovery, deterministic concurrency and settlement boundaries without weakening
Koschei's capability model.
