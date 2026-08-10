import matching

fn render(result: Option<Trade>) -> String {
    return match result {
        Some(trade) => "TRADE maker={trade.maker_id} taker={trade.taker_id} price_ticks={trade.price_ticks} quantity_lots={trade.quantity_lots}",
        None => "NO_TRADE",
    }
}

fn main() {
    // Resting sell is older, therefore it is maker and fixes execution price.
    let resting_sell = Order {
        id: "S-0001",
        side: Sell(),
        price_ticks: 10100,
        quantity_lots: 40,
        sequence: 10,
    }
    let incoming_buy = Order {
        id: "B-0001",
        side: Buy(),
        price_ticks: 10200,
        quantity_lots: 25,
        sequence: 20,
    }
    println(render(matching.match_pair(incoming_buy, resting_sell)))

    // Price does not cross the resting ask.
    let low_buy = Order {
        id: "B-0002",
        side: Buy(),
        price_ticks: 10099,
        quantity_lots: 10,
        sequence: 21,
    }
    println(render(matching.match_pair(low_buy, resting_sell)))

    // Zero quantity is invalid and cannot produce a trade.
    let invalid_sell = Order {
        id: "S-0002",
        side: Sell(),
        price_ticks: 10000,
        quantity_lots: 0,
        sequence: 22,
    }
    println(render(matching.match_pair(incoming_buy, invalid_sell)))
}
