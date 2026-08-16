fn fee_for(notional: Int, basis_points: Int) -> Int {
    if notional <= 0 {
        return 0
    }
    if basis_points <= 0 {
        return 0
    }
    return notional * basis_points / 10000
}

fn maker_fee(notional: Int) -> Int {
    return fee_for(notional, 2)
}

fn taker_fee(notional: Int) -> Int {
    return fee_for(notional, 5)
}

fn main() {}
