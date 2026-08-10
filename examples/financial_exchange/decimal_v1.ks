fn main() {
    let bid = decimal("101.2500", 4) or return
    let fee = decimal("0.1250", 4) or return
    let total = decimal_add(bid, fee) or return
    let lower = decimal("101.2000", 4) or return
    let order = decimal_cmp(lower, bid) or return

    println(decimal_text(bid))
    println(decimal_text(total))
    println(order)
    println(bid)
}
