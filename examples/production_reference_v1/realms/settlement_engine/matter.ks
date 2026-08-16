import matching_engine
import fee_engine
import ledger_engine

fn buyer_cash_delta(resting_price_ticks: Int, trade_quantity_lots: Int) -> Int {
    let notional = matching_engine.trade_notional(resting_price_ticks, trade_quantity_lots)
    let fee = fee_engine.taker_fee(notional)
    return ledger_engine.buyer_cash_delta(notional, fee)
}

fn seller_cash_delta(resting_price_ticks: Int, trade_quantity_lots: Int) -> Int {
    let notional = matching_engine.trade_notional(resting_price_ticks, trade_quantity_lots)
    let fee = fee_engine.maker_fee(notional)
    return ledger_engine.seller_cash_delta(notional, fee)
}

fn total_fees(resting_price_ticks: Int, trade_quantity_lots: Int) -> Int {
    let notional = matching_engine.trade_notional(resting_price_ticks, trade_quantity_lots)
    return fee_engine.taker_fee(notional) + fee_engine.maker_fee(notional)
}

fn settlement_balanced(resting_price_ticks: Int, trade_quantity_lots: Int) -> Bool {
    let buyer = buyer_cash_delta(resting_price_ticks, trade_quantity_lots)
    let seller = seller_cash_delta(resting_price_ticks, trade_quantity_lots)
    let fees = total_fees(resting_price_ticks, trade_quantity_lots)
    return ledger_engine.cash_conserved(buyer, seller, fees)
}

fn main() {}
