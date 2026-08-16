import matching_engine
import settlement_engine
import report_engine
import json_gateway
import dispatch_runtime

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

fn dispatch_total() -> Int or Error {
    let squares = dispatch_runtime.parallel_square([1, 2, 3, 4]) or return Error("dispatch failed")
    let mut total = 0
    for square in squares {
        total = total + square
    }
    return total
}

fn main() {
    println(process(10200, 25, 10100, 40, 500000, 100))
    println(process(10099, 10, 10100, 40, 500000, 100))
    println(process(10200, 25, 10100, 40, 100000, 100))

    let canonical = json_gateway.canonicalize("\{\"b\":2,\"a\":1.00\}") or return
    println(canonical)

    let total = dispatch_total() or return
    println(total)
}
