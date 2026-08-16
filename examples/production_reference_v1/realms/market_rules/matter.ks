import order_core

fn buy_crosses(buy_price_ticks: Int, sell_price_ticks: Int) -> Bool {
    if !order_core.positive(buy_price_ticks) {
        return false
    }
    if !order_core.positive(sell_price_ticks) {
        return false
    }
    return buy_price_ticks >= sell_price_ticks
}

fn execution_quantity(incoming_lots: Int, resting_lots: Int) -> Int {
    if incoming_lots <= 0 {
        return 0
    }
    if resting_lots <= 0 {
        return 0
    }
    if incoming_lots < resting_lots {
        return incoming_lots
    }
    return resting_lots
}

fn execution_price(resting_price_ticks: Int) -> Int {
    return resting_price_ticks
}

fn main() {}
