fn buyer_asset_delta(quantity_lots: Int) -> Int {
    if quantity_lots <= 0 {
        return 0
    }
    return quantity_lots
}

fn seller_asset_delta(quantity_lots: Int) -> Int {
    return 0 - buyer_asset_delta(quantity_lots)
}

fn buyer_cash_delta(notional: Int, fee: Int) -> Int {
    if notional <= 0 {
        return 0
    }
    return 0 - (notional + fee)
}

fn seller_cash_delta(notional: Int, fee: Int) -> Int {
    if notional <= 0 {
        return 0
    }
    return notional - fee
}

fn cash_conserved(buyer_delta: Int, seller_delta: Int, fees: Int) -> Bool {
    return buyer_delta + seller_delta + fees == 0
}

fn main() {}
