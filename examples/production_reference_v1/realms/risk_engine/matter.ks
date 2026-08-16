import order_core

fn within_notional_limit(price_ticks: Int, quantity_lots: Int, max_notional: Int) -> Bool {
    if !order_core.valid_order(price_ticks, quantity_lots) {
        return false
    }
    if max_notional <= 0 {
        return false
    }
    return order_core.notional(price_ticks, quantity_lots) <= max_notional
}

fn within_quantity_limit(quantity_lots: Int, max_quantity_lots: Int) -> Bool {
    if quantity_lots <= 0 {
        return false
    }
    return quantity_lots <= max_quantity_lots
}

fn approved(price_ticks: Int, quantity_lots: Int, max_notional: Int, max_quantity_lots: Int) -> Bool {
    if !within_notional_limit(price_ticks, quantity_lots, max_notional) {
        return false
    }
    return within_quantity_limit(quantity_lots, max_quantity_lots)
}

fn main() {}
