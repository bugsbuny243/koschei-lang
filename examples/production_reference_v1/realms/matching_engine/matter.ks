import order_core
import market_rules
import risk_engine

fn trade_quantity(
    buy_price_ticks: Int,
    buy_quantity_lots: Int,
    sell_price_ticks: Int,
    sell_quantity_lots: Int,
    max_notional: Int,
    max_quantity_lots: Int,
) -> Int {
    if !order_core.valid_order(buy_price_ticks, buy_quantity_lots) {
        return 0
    }
    if !order_core.valid_order(sell_price_ticks, sell_quantity_lots) {
        return 0
    }
    if !risk_engine.approved(buy_price_ticks, buy_quantity_lots, max_notional, max_quantity_lots) {
        return 0
    }
    if !market_rules.buy_crosses(buy_price_ticks, sell_price_ticks) {
        return 0
    }
    return market_rules.execution_quantity(buy_quantity_lots, sell_quantity_lots)
}

fn trade_notional(resting_price_ticks: Int, trade_quantity_lots: Int) -> Int {
    return order_core.notional(market_rules.execution_price(resting_price_ticks), trade_quantity_lots)
}

fn matched(trade_quantity_lots: Int) -> Bool {
    return trade_quantity_lots > 0
}

fn main() {}
