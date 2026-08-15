import matching_engine
import settlement_engine

fn render(resting_price_ticks: Int, trade_quantity_lots: Int) -> String {
    let notional = matching_engine.trade_notional(resting_price_ticks, trade_quantity_lots)
    let buyer_cash = settlement_engine.buyer_cash_delta(resting_price_ticks, trade_quantity_lots)
    let seller_cash = settlement_engine.seller_cash_delta(resting_price_ticks, trade_quantity_lots)
    let fees = settlement_engine.total_fees(resting_price_ticks, trade_quantity_lots)
    let balanced = settlement_engine.settlement_balanced(resting_price_ticks, trade_quantity_lots)
    return "trade quantity={trade_quantity_lots} price={resting_price_ticks} notional={notional} buyer_cash={buyer_cash} seller_cash={seller_cash} fees={fees} balanced={balanced}"
}

fn main() {}
