// Koschei Financial Infrastructure P0: deterministic pair matcher.
//
// Money is deliberately represented as integer price ticks and quantity lots.
// No Float enters the matching core.  The scale belongs to the market contract,
// not to host-language floating point behavior.

enum Side {
    Buy,
    Sell,
}

struct Order {
    id: String,
    side: Side,
    price_ticks: Int,
    quantity_lots: Int,
    sequence: Int,
}

struct Trade {
    maker_id: String,
    taker_id: String,
    price_ticks: Int,
    quantity_lots: Int,
}

fn min_int(left: Int, right: Int) -> Int {
    if left <= right {
        return left
    }
    return right
}

fn valid_order(order: Order) -> Bool {
    return order.price_ticks > 0 && order.quantity_lots > 0 && order.sequence >= 0
}

fn crosses(buy: Order, sell: Order) -> Bool {
    return buy.side == Buy() && sell.side == Sell() && buy.price_ticks >= sell.price_ticks
}

fn match_pair(buy: Order, sell: Order) -> Option<Trade> {
    if !valid_order(buy) || !valid_order(sell) {
        return None()
    }
    if !crosses(buy, sell) {
        return None()
    }

    let quantity = min_int(buy.quantity_lots, sell.quantity_lots)

    // Price-time rule: the older order is maker and its limit price is the
    // deterministic execution price. Equal sequence numbers are rejected by
    // the caller's sequencing layer in later phases; P0 resolves ties to sell.
    if buy.sequence < sell.sequence {
        return Some(Trade {
            maker_id: buy.id,
            taker_id: sell.id,
            price_ticks: buy.price_ticks,
            quantity_lots: quantity,
        })
    }

    return Some(Trade {
        maker_id: sell.id,
        taker_id: buy.id,
        price_ticks: sell.price_ticks,
        quantity_lots: quantity,
    })
}
