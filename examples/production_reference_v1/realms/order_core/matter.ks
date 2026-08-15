fn positive(value: Int) -> Bool {
    return value > 0
}

fn valid_order(price_ticks: Int, quantity_lots: Int) -> Bool {
    if price_ticks <= 0 {
        return false
    }
    if quantity_lots <= 0 {
        return false
    }
    return true
}

fn notional(price_ticks: Int, quantity_lots: Int) -> Int {
    if !valid_order(price_ticks, quantity_lots) {
        return 0
    }
    return price_ticks * quantity_lots
}

fn main() {}
