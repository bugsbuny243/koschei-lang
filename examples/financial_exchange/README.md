# Financial Exchange Reference — P0

This directory is Koschei's first financial-infrastructure reference workload.
It is intentionally small: one deterministic pair matcher, not a production
exchange.

## Security / determinism contract

- Prices are integer `price_ticks`; quantities are integer `quantity_lots`.
- `Float` is forbidden in the financial core.
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

## What P0 does not claim

P0 is not a full order book, venue, custody system, settlement system, or
regulated exchange. It exists to turn financial correctness requirements into
executable compiler/runtime tests. The next phases add exact decimal contracts,
book-level price-time priority, recovery, concurrency and settlement boundaries
without weakening Koschei's capability model.
