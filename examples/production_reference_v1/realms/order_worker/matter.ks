import matching_engine
import settlement_engine
import report_engine

fn process(
    buy_price_ticks: Int,
    buy_quantity_lots: Int,
    sell_price_ticks: Int,
    sell_quantity_lots: Int,
    max_notional: Int,
    max_quantity_lots: Int,
) -> String {
    let quantity = matching_engine.trade_quantity(
        buy_price_ticks,
        buy_quantity_lots,
        sell_price_ticks,
        sell_quantity_lots,
        max_notional,
        max_quantity_lots,
    )
    return report_engine.render(sell_price_ticks, quantity)
}

fn main() {
    println(process(10200, 25, 10100, 40, 500000, 100))
    println(process(10099, 10, 10100, 40, 500000, 100))
    println(process(10200, 25, 10100, 40, 100000, 100))
}
